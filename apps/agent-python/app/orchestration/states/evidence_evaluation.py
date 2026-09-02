"""State handler for claim-level evidence acceptance, conflict and abstention."""

from __future__ import annotations

from app.evidence.claim_decision import TransientEvidence, evaluate_claims
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.report import RetrievalReport
from app.orchestration.state_contracts import AgentState, StateContext, StateResult


class EvidenceEvaluationHandler:
    async def run(self, context: StateContext) -> StateResult:
        raw_plans = context.artifacts.get(AgentState.RETRIEVAL_PLAN.value, {}).get(
            "retrieval_plans", []
        )
        plans = [RetrievalPlan.model_validate(item) for item in raw_plans]
        raw_reports = context.artifacts.get(AgentState.HYBRID_RETRIEVE.value, {}).get(
            "retrieval_reports", []
        )
        reports = []
        malformed = 0
        for item in raw_reports:
            try:
                reports.append(RetrievalReport.model_validate(item))
            except Exception:
                malformed += 1
        gap_artifact = context.artifacts.get(AgentState.LIVE_GAP_FILL.value)
        transient = []
        for item in (gap_artifact or {}).get("transient_evidence", []):
            try:
                transient.append(TransientEvidence.model_validate(item))
            except Exception:
                malformed += 1

        evaluation = evaluate_claims(
            plans=plans,
            reports=reports,
            transient_evidence=transient,
        )
        output = {
            **evaluation.model_dump(mode="json"),
            "malformed_artifact_count": malformed,
            "abstain": False,
        }
        if evaluation.coverage_report.all_required_covered:
            return StateResult.succeeded(next_state=AgentState.COMPOSE, output=output)
        if gap_artifact is None and context.budget.used_tool_calls < context.budget.max_tool_calls:
            return StateResult.succeeded(next_state=AgentState.LIVE_GAP_FILL, output=output)

        output["abstain"] = True
        output["failure_code"] = "required_evidence_missing"
        return StateResult.succeeded(next_state=AgentState.SAFE_FAILURE, output=output)


__all__ = ["EvidenceEvaluationHandler"]
