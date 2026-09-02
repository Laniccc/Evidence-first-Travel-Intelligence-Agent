"""Remove unsupported answer claims before delivery."""

from app.composition.answer_claim import AnswerClaim
from app.evidence.citation_checker import CitationChecker, CitationReport
from app.orchestration.state_contracts import AgentState, StateContext, StateResult


class CitationGuardHandler:
    async def run(self, context: StateContext) -> StateResult:
        composition = context.artifacts.get(AgentState.COMPOSE.value, {})
        claims = [
            AnswerClaim.model_validate(item)
            for item in composition.get("answer_claims", [])
        ]
        evidence_index = composition.get("evidence_index", {})
        report = CitationChecker.check(claims=claims, evidence_index=evidence_index)
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
        if report.safe_failure:
            output["failure_code"] = "all_hard_facts_removed"
            return StateResult.succeeded(next_state=AgentState.SAFE_FAILURE, output=output)
        return StateResult.succeeded(next_state=AgentState.DELIVER, output=output)


__all__ = ["CitationGuardHandler"]
