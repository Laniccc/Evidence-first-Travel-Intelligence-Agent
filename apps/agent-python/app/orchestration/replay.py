"""Replay immutable original artifacts, never re-evaluate with current policy."""
from uuid import uuid4

from pydantic import BaseModel

from app.contracts.mcp_evidence import digest_json
from app.contracts.response import AgentQueryResponse
from app.orchestration.agent_core_models import RunRecord
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.state_contracts import StateContext


class ReplayResult(BaseModel):
    run: RunRecord
    response: AgentQueryResponse


class ReplayService:
    def __init__(self, store: SQLiteRunStore):
        self._store = store

    async def replay(self, *, query_id: str, from_state: str = "evidence_evaluate"):
        if from_state != "evidence_evaluate":
            raise ValueError("only replay from evidence_evaluate is supported")
        source = self._store.latest_original_run_for_query(query_id)
        try:
            saved = self._store.latest_state_output(source.run_id, "delivery_snapshot")
        except KeyError:
            raise ValueError("replay_snapshot_unavailable") from None
        snapshot = saved.get("snapshot", {})
        if source.status not in {"succeeded", "failed"} or snapshot.get("schema_version") != "1":
            raise ValueError("replay_snapshot_unavailable")
        if digest_json(snapshot) != saved.get("digest"):
            raise ValueError("replay_snapshot_corrupted")
        original = AgentQueryResponse.model_validate(snapshot["response"])
        if (original.orchestration_summary or {}).get("terminal_state") != source.current_state:
            raise ValueError("replay_terminal_mismatch")
        context = StateContext(run_id="replay-" + str(uuid4()), query_id=query_id,
            session_id=source.session_id, raw_query="[artifact replay]",
            artifacts=snapshot["artifacts"], versions=snapshot["versions"], config_hashes=snapshot["config_hashes"])
        self._store.start_run(run_id=context.run_id, query_id=query_id, session_id=source.session_id,
            query="[artifact replay]", replay_of_run_id=source.run_id, current_state=from_state)
        try:
            for state, output in context.artifacts.items():
                self._store.append_phase_event(run_id=context.run_id, state=state, status="replayed", attempt=1, output=output)
            response = original.model_copy(deep=True, update={"orchestration_summary": {
                **(original.orchestration_summary or {}), "run_id": context.run_id, "replay_of_run_id": source.run_id,
                "replay_mode": "artifact_snapshot", "replay_external_calls": 0, "replay_write_side_effects": 0}})
            for evidence in response.evidence_summary:
                if evidence.get("evidence_id"):
                    self._store.record_evidence(run_id=context.run_id, evidence_id=evidence["evidence_id"], payload=evidence)
            for claim in response.answer_claims:
                self._store.record_answer_claim(run_id=context.run_id, claim_id=claim["claim_id"], payload=claim)
            for decision in (response.citation_report or {}).get("decisions", []):
                self._store.record_citation_decision(run_id=context.run_id, claim_id=decision["claim_id"],
                    status=decision["status"], reason=decision["reason"])
            self._store.save_response_snapshot(context, response)
            run = self._store.finish_run(context.run_id, status=source.status, current_state=source.current_state)
        except Exception:
            self._store.finish_run(context.run_id, status="failed", current_state="failed")
            raise RuntimeError("replay_persistence_failed") from None
        return ReplayResult(run=run, response=response)
