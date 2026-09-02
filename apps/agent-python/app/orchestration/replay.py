"""Artifact-only replay from the evidence evaluation boundary."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel

from app.contracts.response import AgentQueryResponse
from app.orchestration.agent_core_models import RunRecord
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.answer_composition import GroundedCompositionHandler
from app.orchestration.states.citation_guard import CitationGuardHandler
from app.orchestration.states.delivery import DeliveryHandler
from app.orchestration.states.evidence_evaluation import EvidenceEvaluationHandler


class ReplayResult(BaseModel):
    run: RunRecord
    response: AgentQueryResponse


class ReplayService:
    """Re-run deterministic downstream states without touching retrieval systems."""

    def __init__(self, store: SQLiteRunStore) -> None:
        self._store = store

    async def replay(
        self,
        *,
        query_id: str,
        from_state: str = AgentState.EVIDENCE_EVALUATE.value,
    ) -> ReplayResult:
        if from_state != AgentState.EVIDENCE_EVALUATE.value:
            raise ValueError("only replay from evidence_evaluate is supported")

        source = self._store.latest_run_for_query(query_id)
        replay_run_id = f"replay-{uuid4()}"
        run = self._store.start_run(
            run_id=replay_run_id,
            query_id=query_id,
            session_id=source.session_id,
            query="[artifact replay]",
            replay_of_run_id=source.run_id,
            current_state=from_state,
        )
        context = StateContext(
            run_id=run.run_id,
            query_id=query_id,
            session_id=source.session_id,
            raw_query="[artifact replay]",
            current_state=AgentState.EVIDENCE_EVALUATE,
            artifacts={
                AgentState.RETRIEVAL_PLAN.value: self._store.latest_state_output(
                    source.run_id, AgentState.RETRIEVAL_PLAN.value
                ),
                AgentState.HYBRID_RETRIEVE.value: self._store.latest_state_output(
                    source.run_id, AgentState.HYBRID_RETRIEVE.value
                ),
            },
        )

        await self._run_state(
            context,
            AgentState.EVIDENCE_EVALUATE,
            EvidenceEvaluationHandler(),
            expected_next=AgentState.COMPOSE,
        )
        await self._run_state(
            context,
            AgentState.COMPOSE,
            GroundedCompositionHandler(),
            expected_next=AgentState.CITATION_GUARD,
        )
        await self._run_state(
            context,
            AgentState.CITATION_GUARD,
            CitationGuardHandler(),
            expected_next=AgentState.DELIVER,
        )

        response = await DeliveryHandler().build_response(context)
        self._persist_result_artifacts(context, response)
        run = self._store.finish_run(
            replay_run_id, status="succeeded", current_state=AgentState.DELIVER.value
        )
        return ReplayResult(run=run, response=response)

    async def _run_state(
        self,
        context: StateContext,
        state: AgentState,
        handler,
        *,
        expected_next: AgentState,
    ) -> None:
        context.current_state = state
        result = await handler.run(context)
        if result.next_state != expected_next:
            raise RuntimeError(
                f"artifact replay stopped at {state.value}: {result.next_state.value}"
            )
        context.artifacts[state.value] = result.output
        self._store.append_phase_event(
            run_id=context.run_id,
            state=state.value,
            status=result.status,
            attempt=(result.recovery.attempt if result.recovery else 1),
            output=result.output,
            failure_code=(result.failure.code if result.failure else None),
            recovery_strategy=(result.recovery.strategy if result.recovery else None),
        )

    def _persist_result_artifacts(
        self, context: StateContext, response: AgentQueryResponse
    ) -> None:
        guarded = context.artifacts[AgentState.CITATION_GUARD.value]
        for evidence_id, payload in guarded.get("evidence_index", {}).items():
            self._store.record_evidence(
                run_id=context.run_id, evidence_id=evidence_id, payload=payload
            )
        for claim in response.answer_claims:
            self._store.record_answer_claim(
                run_id=context.run_id, claim_id=claim["claim_id"], payload=claim
            )
        report = response.citation_report or {}
        for decision in report.get("decisions", []):
            self._store.record_citation_decision(
                run_id=context.run_id,
                claim_id=decision["claim_id"],
                status=decision["status"],
                reason=decision["reason"],
            )
        self._store.record_metric(
            run_id=context.run_id,
            name="citation_precision",
            value=float(report.get("citation_precision", 0.0)),
        )


__all__ = ["ReplayResult", "ReplayService"]
