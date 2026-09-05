"""Single production state machine for the bounded Evidence-first RAG product."""

from __future__ import annotations

from uuid import uuid4

from app.contracts.response import AgentQueryResponse, TravelQueryResponse
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.state_audit import InMemoryStateAuditStore, SQLiteStateAuditStore, StateAuditEvent
from app.orchestration.state_contracts import AgentState, StateContext, StatePolicy, StateFailure, FailureClass
from app.orchestration.state_runtime import StateRuntime
from app.orchestration.publication_observation import publication_snapshot
from app.orchestration.states.answer_composition import GroundedCompositionHandler
from app.orchestration.states.citation_guard import CitationGuardHandler
from app.orchestration.states.context_loading import ContextLoadingHandler
from app.orchestration.states.delivery import DeliveryHandler
from app.orchestration.states.evidence_evaluation import EvidenceEvaluationHandler
from app.orchestration.states.hybrid_retrieval import HybridRetrievalHandler
from app.orchestration.states.ingress import InMemoryIdempotencyStore, IngressHandler
from app.orchestration.states.live_gap_fill import LiveGapFillHandler
from app.orchestration.states.llm_understanding import UnderstandingHandler
from app.orchestration.states.retrieval_planning import RetrievalPlanningHandler
from app.orchestration.states.routing import RouteHandler, RoutedTaskHandler


class UnavailableGapFillTool:
    async def fetch(self, task: dict, *, attempt: int) -> dict:
        del task, attempt
        raise RuntimeError("live gap tool is not configured")


class TravelAgentStateMachine:
    """Compose state handlers once and expose one auditable request path."""

    def __init__(
        self,
        *,
        retriever=None,
        attraction_resolver=None,
        attraction_matcher=None,
        primary_understanding=None,
        understanding_timeout_seconds=8.0,
        composer=None,
        composer_timeout_seconds=2.0,
        promotion_handler=None,
        index_job_reader=None,
        retrieval_top_k: int = 3,
        history_loader=None,
        gap_tool=None,
        run_store: SQLiteRunStore | None = None,
        audit=None,
        logger=None,
    ) -> None:
        self._run_store = run_store
        self._index_job_reader = index_job_reader
        self._audit = audit or (
            SQLiteStateAuditStore(run_store, logger=logger)
            if run_store
            else InMemoryStateAuditStore()
        )
        self._delivery = DeliveryHandler()
        handlers = {
            AgentState.INGRESS: IngressHandler(
                idempotency_store=InMemoryIdempotencyStore()
            ),
            AgentState.CONTEXT: ContextLoadingHandler(history_loader=history_loader),
            AgentState.UNDERSTAND: UnderstandingHandler(
                primary=primary_understanding,
                primary_timeout_seconds=understanding_timeout_seconds,
                attraction_matcher=attraction_matcher,
            ),
            AgentState.ROUTE: RouteHandler(),
            AgentState.FACT_QUERY: RoutedTaskHandler(AgentState.FACT_QUERY),
            AgentState.SUITABILITY: RoutedTaskHandler(AgentState.SUITABILITY),
            AgentState.COMPARISON: RoutedTaskHandler(AgentState.COMPARISON),
            AgentState.RETRIEVAL_PLAN: RetrievalPlanningHandler(
                attraction_resolver=attraction_resolver or (lambda name: None),
                top_k=retrieval_top_k,
            ),
            AgentState.HYBRID_RETRIEVE: HybridRetrievalHandler(
                retriever=retriever or _UnavailableRetriever()
            ),
            AgentState.LIVE_GAP_FILL: LiveGapFillHandler(
                tool=gap_tool or UnavailableGapFillTool()
            ),
            AgentState.EVIDENCE_EVALUATE: EvidenceEvaluationHandler(promotion_enabled=promotion_handler is not None),
            AgentState.COMPOSE: GroundedCompositionHandler(composer=composer, timeout_seconds=composer_timeout_seconds),
            AgentState.CITATION_GUARD: CitationGuardHandler(),
        }
        if promotion_handler is not None:
            handlers[AgentState.KNOWLEDGE_PROMOTE] = promotion_handler
        self._runtime = StateRuntime(
            handlers=handlers, audit=self._audit,
            policies={AgentState.LIVE_GAP_FILL: StatePolicy(timeout_seconds=25),
                      AgentState.UNDERSTAND: StatePolicy(timeout_seconds=understanding_timeout_seconds + 2),
                      AgentState.KNOWLEDGE_PROMOTE: StatePolicy(timeout_seconds=35)},
        )

    async def run(
        self,
        query: str,
        user_context: dict | None = None,
        session_id: str | None = None,
        *,
        debug: bool = False,
        trace_id: str | None = None,
    ) -> TravelQueryResponse:
        del debug
        run_id = str(uuid4())
        query_id = str(uuid4())
        resolved_session_id = session_id or str(uuid4())
        context = StateContext(
            run_id=run_id,
            session_id=resolved_session_id,
            query_id=query_id,
            raw_query=query,
            user_context=user_context or {},
            idempotency_key=(user_context or {}).get("idempotency_key"),
            trace_id=trace_id or str(uuid4()),
        )
        if self._run_store:
            self._run_store.start_run(
                run_id=run_id,
                query_id=query_id,
                session_id=resolved_session_id,
                query=query,
            )

        try:
            outcome = await self._runtime.run(context)
        except Exception:
            return self._fail_terminal(context, "audit_persistence_unavailable", must_raise=True)
        try:
            response = await self._build_response(outcome.terminal_state, context, outcome.failure)
        except Exception:
            return self._fail_terminal(context, "terminal_projection_failed")
        try:
            self._persist_response(context, response)
            if self._run_store:
                self._run_store.save_response_snapshot(context, response)
            if self._run_store:
                status = "failed" if outcome.terminal_state == AgentState.FAILED else "succeeded"
                self._run_store.finish_run(run_id, status=status, current_state=outcome.terminal_state.value)
        except Exception:
            return self._fail_terminal(context, "audit_persistence_unavailable", must_raise=True)
        return response

    def _fail_terminal(self, context, code, *, must_raise=False):
        failure = StateFailure(category=FailureClass.INTERNAL, code=code,
                               message="The run could not be completed safely.", recoverable=False)
        audit_failed = False
        try:
            self._audit.append(StateAuditEvent.failed(context, AgentState.DELIVER, attempt=1, failure=failure))
        except Exception:
            audit_failed = True
        try:
            if self._run_store:
                self._run_store.finish_run(context.run_id, status="failed", current_state="failed")
        except Exception:
            audit_failed = True
        if must_raise or audit_failed:
            raise RuntimeError("audit_persistence_unavailable") from None
        return AgentQueryResponse(answer="当前结果无法安全交付，请稍后重试。",
            session_id=context.session_id, query_id=context.query_id, limitations=[code], confidence=0,
            orchestration_summary={"run_id": context.run_id, "terminal_state": "failed",
                "trace_id": context.trace_id, "failure": failure.model_dump(mode="json")})

    async def _build_response(self, terminal, context, failure) -> AgentQueryResponse:
        if terminal == AgentState.DELIVER:
            cached = context.artifacts.get(AgentState.INGRESS.value, {}).get(
                "cached_response"
            )
            response = (
                AgentQueryResponse.model_validate(cached)
                if cached
                else await self._delivery.build_response(context)
            )
        else:
            terminal_output = next(reversed(context.artifacts.values()), {})
            answer = terminal_output.get("question") or terminal_output.get("message")
            response = AgentQueryResponse(
                answer=answer or "当前证据不足，无法可靠回答。",
                session_id=context.session_id,
                query_id=context.query_id,
                limitations=[terminal_output.get("failure_code") or terminal.value],
                confidence=0.0,
            )
        timeline = [
            event.model_dump(mode="json")
            for event in self._audit.for_run(context.run_id)
        ]
        summary = dict(response.orchestration_summary or {})
        summary.update(
            {
                "run_id": context.run_id,
                "terminal_state": terminal.value,
                "trace_id": context.trace_id,
                "steps": sum(
                    item["event_type"] == "transition_committed" for item in timeline
                ),
                "state_audit": timeline,
                "failure": failure.model_dump(mode="json") if failure else None,
            }
        )
        promotion, sync = await publication_snapshot(context.artifacts.get("knowledge_promote"),
                                                     job_reader=self._index_job_reader)
        return response.model_copy(
            update={
                "session_id": context.session_id,
                "query_id": context.query_id,
                "orchestration_summary": summary,
                "promotion_summary": promotion,
                "index_sync_status": sync,
            }
        )

    def _persist_response(
        self, context: StateContext, response: AgentQueryResponse
    ) -> None:
        if not self._run_store:
            return
        guarded = context.artifacts.get(AgentState.CITATION_GUARD.value, {})
        for evidence_id, payload in guarded.get("evidence_index", {}).items():
            self._run_store.record_evidence(
                run_id=context.run_id, evidence_id=evidence_id, payload=payload
            )
        for claim in response.answer_claims:
            self._run_store.record_answer_claim(
                run_id=context.run_id,
                claim_id=claim["claim_id"],
                payload=claim,
            )
        report = response.citation_report or {}
        for decision in report.get("decisions", []):
            self._run_store.record_citation_decision(
                run_id=context.run_id,
                claim_id=decision["claim_id"],
                status=decision["status"],
                reason=decision["reason"],
            )
        self._run_store.record_metric(
            run_id=context.run_id,
            name="citation_precision",
            value=float(report.get("citation_precision", 0.0)),
        )


class _UnavailableRetriever:
    async def aretrieve(self, plan):
        del plan
        raise RuntimeError("retrieval dependency is not configured")


__all__ = ["TravelAgentStateMachine", "TravelQueryResponse", "UnavailableGapFillTool"]
