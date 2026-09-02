"""One logical live gap task with at most two audited execution attempts."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.evidence.claim_decision import TransientEvidence
from app.evidence.retrieval.contracts import RetrievalPlan
from app.orchestration.state_contracts import AgentState, StateContext, StateResult


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
            context.budget = context.budget.consume_tool_call()
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
        task = {
            "subtask_id": plan.subtask_id if plan else context.query_id,
            "attraction_id": plan.attraction_ids[0] if plan else None,
            "fact_type": _fact_type_from_item(missing)
            or (plan.fact_types[0].value if plan and plan.fact_types else None),
            "query_text": plan.query_text if plan else context.raw_query,
        }
        attempts = []
        evidence = []
        for attempt_number in range(1, self.MAX_ATTEMPTS + 1):
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
