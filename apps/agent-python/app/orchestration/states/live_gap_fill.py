"""One logical live gap task with at most two audited execution attempts."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.evidence.claim_decision import TransientEvidence
from app.evidence.baidu_normalizer import normalize_baidu_evidence, BaiduEvidenceError
from app.contracts.mcp_evidence import McpEvidenceEnvelope
from app.integrations.mcp.tool_catalog import MCPBoundaryError
from app.evidence.retrieval.contracts import RetrievalPlan
from app.orchestration.state_contracts import AgentState, StateContext, StateResult, RecoveryRecord
from app.governance.failure_reason import FailureClass


class GapFillTool(Protocol):
    async def fetch(self, task: dict[str, Any], *, attempt: int) -> dict[str, Any]: ...


class GapFillAttempt(BaseModel):
    attempt: int = Field(ge=1, le=2)
    status: str
    failure_code: str | None = None


class LiveGapFillHandler:
    MAX_ATTEMPTS = 2

    def __init__(self, *, tool: GapFillTool, pending_writer=None) -> None:
        self._tool = tool
        self._pending_writer = pending_writer

    async def run(self, context: StateContext) -> StateResult:
        if AgentState.LIVE_GAP_FILL.value in context.artifacts:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "gap_fill_already_attempted"},
            )
        try:
            context.budget = context.budget.consume_gap_task()
        except ValueError:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "gap_fill_budget_exhausted"},
            )

        plans = [
            RetrievalPlan.model_validate(item)
            for item in context.artifacts.get(AgentState.RETRIEVAL_PLAN.value, {}).get(
                "retrieval_plans", []
            )
        ]
        coverage_items = context.artifacts.get(AgentState.EVIDENCE_EVALUATE.value, {}).get(
            "coverage_report", {}
        ).get("items", [])
        missing = next((item for item in coverage_items if not item.get("covered")), None)
        plan = plans[0] if plans else None
        if missing and len(plans) > 1:
            claim = missing.get("claim_type", "")
            candidates = [p for p in plans if any(claim == f"{p.subtask_id}:{f.value}" for f in p.fact_types)]
            if len(candidates) != 1:
                return StateResult.succeeded(next_state=AgentState.EVIDENCE_EVALUATE,
                    output={"logical_gap_task_count": 1, "attempts": [], "transient_evidence": [],
                            "failure_code": "ambiguous_gap_target", "tool_call_attempt_count": 0})
            plan = candidates[0]
        task = {
            "subtask_id": plan.subtask_id if plan else context.query_id,
            "attraction_id": plan.attraction_ids[0] if plan else None,
            "fact_type": _fact_type_from_item(missing)
            or (plan.fact_types[0].value if plan and plan.fact_types else None),
            "query_text": plan.query_text if plan else context.raw_query,
            "require_explicit_temporal_coverage": plan.require_explicit_temporal_coverage if plan else False,
        }
        if hasattr(self._tool, "fetch_gap"):
            def before_call():
                try:
                    context.budget = context.budget.consume_tool_call()
                except ValueError:
                    raise MCPBoundaryError("tool_budget_exhausted") from None

            payload = await self._tool.fetch_gap(task, before_call=before_call)
            evidence, envelopes = [], []
            code = payload.get("failure_code")
            if payload.get("envelope"):
                try:
                    envelope = McpEvidenceEnvelope.model_validate(payload["envelope"])
                    if envelope.attraction_id != task["attraction_id"]:
                        raise BaiduEvidenceError("entity_mismatch")
                    item = normalize_baidu_evidence(envelope, fact_type=task["fact_type"],
                                                    subtask_id=task["subtask_id"])
                    evidence.append(item.model_dump(mode="json"))
                    envelopes.append(envelope.model_dump(mode="json"))
                except BaiduEvidenceError as exc:
                    code = str(exc)
                except ValueError:
                    code = "malformed_payload"
            output = {"logical_gap_task_count": 1, "gap_task": task,
                        "attempts": payload.get("attempts", []),
                        "tool_call_attempt_count": len(payload.get("attempts", [])),
                        "session_restarts": payload.get("session_restarts", 0),
                        "failure_code": code, "transient_evidence": evidence,
                        "mcp_envelopes": envelopes, "active_index_updated": False}
            failures = [a for a in output["attempts"] if a["status"] == "failed"]
            if code or failures:
                reason = code or failures[-1].get("failure_code")
                category = {
                    "tool_timeout": FailureClass.TIMEOUT,
                    "gap_deadline_exceeded": FailureClass.TIMEOUT,
                    "rate_limit": FailureClass.RATE_LIMIT,
                    "tool_budget_exhausted": FailureClass.BUDGET_EXHAUSTED,
                    "unsupported_fact": FailureClass.POLICY_DENIED,
                    "temporal_scope_unsupported": FailureClass.POLICY_DENIED,
                    "invalid_arguments": FailureClass.VALIDATION,
                    "malformed_payload": FailureClass.PARSE_ERROR,
                }.get(reason, FailureClass.DEPENDENCY_UNAVAILABLE)
                return StateResult(status="recovered", next_state=AgentState.EVIDENCE_EVALUATE,
                    output=output, recovery=RecoveryRecord(
                        strategy="gap_unavailable" if code else "gap_retried",
                        recovered_from=category, attempt=max(1, len(output["attempts"]))))
            return StateResult.succeeded(next_state=AgentState.EVIDENCE_EVALUATE, output=output)
        attempts = []
        evidence = []
        for attempt_number in range(1, self.MAX_ATTEMPTS + 1):
            try:
                context.budget = context.budget.consume_tool_call()
            except ValueError:
                break
            try:
                payload = await self._tool.fetch(task, attempt=attempt_number)
                item = TransientEvidence.model_validate(payload)
            except Exception as exc:
                attempts.append(
                    GapFillAttempt(
                        attempt=attempt_number,
                        status="failed",
                        failure_code=_failure_code(exc),
                    )
                )
                continue
            evidence.append(item)
            attempts.append(GapFillAttempt(attempt=attempt_number, status="success"))
            if self._pending_writer is not None:
                self._pending_writer.write_pending(item.model_dump(mode="json"))
            break

        return StateResult.succeeded(
            next_state=AgentState.EVIDENCE_EVALUATE,
            output={
                "logical_gap_task_count": 1,
                "gap_task": task,
                "attempts": [item.model_dump(mode="json") for item in attempts],
                "transient_evidence": [item.model_dump(mode="json") for item in evidence],
                "active_index_updated": False,
                "tool_call_attempt_count": len(attempts),
            },
        )


def _fact_type_from_item(item: dict | None) -> str | None:
    if not item:
        return None
    return str(item.get("claim_type", "")).rsplit(":", maxsplit=1)[-1] or None


def _failure_code(exc: Exception) -> str:
    message = str(exc).casefold()
    if "429" in message or "rate" in message:
        return "rate_limit"
    if "validation" in type(exc).__name__.casefold() or "source_url" in message:
        return "malformed_payload"
    return "tool_failure"


__all__ = ["GapFillAttempt", "GapFillTool", "LiveGapFillHandler"]
