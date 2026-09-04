"""Remove unsupported answer claims before delivery."""
from datetime import datetime

from app.composition.answer_claim import AnswerClaim
from app.evidence.citation_checker import CitationChecker, CitationReport
from app.orchestration.state_contracts import AgentState, StateContext, StateResult
from app.orchestration.states.answer_composition import _build_evidence_index


class CitationGuardHandler:
    async def run(self, context: StateContext) -> StateResult:
        composition = context.artifacts.get(AgentState.COMPOSE.value, {})
        claims = [
            AnswerClaim.model_validate(item)
            for item in composition.get("answer_claims", [])
        ]
        evaluation = context.artifacts.get(AgentState.EVIDENCE_EVALUATE.value)
        evidence_index = _build_evidence_index(context) if evaluation is not None else composition.get("evidence_index", {})
        times = {p["subtask_id"]: p["as_of"] for p in context.artifacts.get("retrieval_plan", {}).get("retrieval_plans", [])}
        evaluated_at = (evaluation or {}).get("evaluated_at")
        report = CitationChecker.check(claims=claims, evidence_index=evidence_index,
            approved_decisions=(evaluation or {}).get("claim_decisions", []), as_of_by_subtask=times,
            evaluated_at=datetime.fromisoformat(evaluated_at) if evaluated_at else None)
        assert isinstance(report, CitationReport)
        supported_ids = set(report.supported_claim_ids)
        supported = [claim for claim in claims if claim.claim_id in supported_ids]
        answer = "\n".join(
            f"- {claim.text}"
            + (
                f"（证据：{', '.join(claim.evidence_ids)}）"
                if claim.evidence_ids
                else ""
            )
            for claim in supported
        )
        output = {
            "answer": answer,
            "supported_claims": [item.model_dump(mode="json") for item in supported],
            "citation_report": report.model_dump(mode="json"),
            "evidence_index": evidence_index,
        }
        if report.safe_failure or not supported:
            output["failure_code"] = "all_hard_facts_removed"
            return StateResult.succeeded(next_state=AgentState.SAFE_FAILURE, output=output)
        return StateResult.succeeded(next_state=AgentState.DELIVER, output=output)


__all__ = ["CitationGuardHandler"]
