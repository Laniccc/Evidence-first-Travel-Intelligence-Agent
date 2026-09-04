"""State boundary around hybrid retrieval and its independent degradations."""

from __future__ import annotations

from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.report import (
    LatencyBreakdown,
    RetrievalAttempt,
    RetrievalReport,
)
from app.governance.failure_reason import FailureClass
from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateResult,
)


class HybridRetrievalHandler:
    def __init__(self, *, retriever) -> None:
        self._retriever = retriever

    async def run(self, context: StateContext) -> StateResult:
        raw_plans = context.artifacts.get(AgentState.RETRIEVAL_PLAN.value, {}).get(
            "retrieval_plans", []
        )
        plans = [RetrievalPlan.model_validate(item) for item in raw_plans]
        if not plans:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "missing_retrieval_plan", "retrieval_reports": []},
            )

        reports = []
        for plan in plans:
            try:
                report = RetrievalReport.model_validate(await self._retriever.aretrieve(plan))
            except Exception as exc:
                code = _failure_code(exc)
                report = _failed_report(plan, code)
            reports.append(report)

        degradations = [report.degradation for report in reports]
        no_usable_evidence = all(not report.final_hits for report in reports)
        next_state = (
            AgentState.LIVE_GAP_FILL if no_usable_evidence else AgentState.EVIDENCE_EVALUATE
        )
        output = {
            "retrieval_reports": [report.model_dump(mode="json") for report in reports],
            "comparison_artifacts": {
                f"comparison:{report.subtask_id}": report.model_dump(mode="json")
                for report in reports
                if report.retrieval_plan.task_type == "comparison"
            },
        }
        degraded = [item for item in degradations if item != "none"]
        if degraded:
            strategy = degraded[0] if len(set(degraded)) == 1 else "partial_retrieval"
            return StateResult(
                status="recovered",
                next_state=next_state,
                output=output,
                recovery=RecoveryRecord(
                    strategy=strategy,
                    recovered_from=_failure_class(reports),
                    attempt=1,
                ),
            )
        return StateResult.succeeded(next_state=next_state, output=output)


def _failed_report(plan: RetrievalPlan, code: str) -> RetrievalReport:
    return RetrievalReport(
        subtask_id=plan.subtask_id,
        retrieval_plan=plan,
        corpus_version="unavailable",
        lexical_attempt=RetrievalAttempt(
            channel="lexical", status="failed", latency_ms=0, failure_code=code
        ),
        dense_attempt=RetrievalAttempt(
            channel="dense", status="failed", latency_ms=0, failure_code=code
        ),
        degradation="all_failed",
        coverage_hints=["retrieval_state_failure"],
        latency_breakdown=LatencyBreakdown(
            lexical_ms=0,
            dense_ms=0,
            fusion_ms=0,
            post_filter_rerank_ms=0,
            total_ms=0,
        ),
    )


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "timeout"
    message = str(exc).casefold()
    if "embedding" in message:
        return "embedding_unavailable"
    if "429" in message or "rate" in message:
        return "rate_limit"
    return "malformed_retrieval_payload"


def _failure_class(reports: list[RetrievalReport]) -> FailureClass:
    codes = {
        attempt.failure_code
        for report in reports
        for attempt in (report.lexical_attempt, report.dense_attempt)
        if attempt.failure_code
    }
    if "timeout" in codes:
        return FailureClass.TIMEOUT
    if "rate_limit" in codes:
        return FailureClass.RATE_LIMIT
    if not any(report.final_hits for report in reports):
        return FailureClass.EMPTY_RESULT
    return FailureClass.DEPENDENCY_UNAVAILABLE


__all__ = ["HybridRetrievalHandler"]
