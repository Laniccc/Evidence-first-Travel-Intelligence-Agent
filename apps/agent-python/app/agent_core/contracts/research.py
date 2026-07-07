"""Research domain contracts for the Deep Research Agent.

Each contract defines the quality gates, evidence requirements, and
composition rules specific to a research task type.
"""

from __future__ import annotations

from typing import Any

from app.agent_core.contracts.base import BaseTaskContract, ContractCheck


class GeneralResearchContract(BaseTaskContract):
    """Contract for general web research tasks.

    Any topic that doesn't match a specialized contract falls here.
    Requirements are moderate: Tier 3+ sources, 2+ sources per sub-question.
    """

    task_class: str = "general_research"

    def research_plan(self, query: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "task_class": self.task_class,
            "search_sources": ["general", "news"],
            "min_sources_per_question": 2,
            "min_source_tier": 3,
            "require_cross_reference": True,
            "max_retries_per_question": 2,
        }

    def review_evidence(
        self, evidence: list[dict[str, Any]], query: str, target: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        adopted = []
        rejected = []
        for ev in evidence:
            tier = ev.get("source_tier", 3)
            has_claims = len(ev.get("claims", [])) > 0
            if tier <= 3 and has_claims:
                adopted.append(ev)
            else:
                rejected.append({"evidence_id": ev.get("evidence_id"), "reason": f"Tier {tier} too low" if tier > 3 else "No extractable claims"})
        return {"adopted": adopted, "rejected": rejected}

    def decide_claim(
        self, review: dict[str, Any], query: str, target: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        adopted = review.get("adopted", [])
        return {
            "decision": "approved" if len(adopted) >= 1 else "needs_revision",
            "adopted_count": len(adopted),
            "rejected_count": len(review.get("rejected", [])),
        }

    def check_claim_decision(self, decision: dict[str, Any]) -> list[ContractCheck]:
        checks = []
        # Gate 4: Evidence sufficiency
        adopted_count = decision.get("adopted_count", 0)
        checks.append(ContractCheck(
            name="evidence_sufficiency",
            status="pass" if adopted_count >= 1 else "fail",
            score=min(1.0, adopted_count / 2.0),
            blocking_issues=[] if adopted_count >= 1 else ["No adopted evidence found"],
        ))
        return checks

    def compose_answer(self, decision: dict[str, Any], query: str) -> dict[str, Any]:
        return {
            "answer_type": "research_report",
            "sections": decision.get("sections", []),
            "citations": decision.get("citations", []),
        }


class TechSurveyContract(GeneralResearchContract):
    """Contract for technology survey / trend research tasks.

    Stricter requirements: Tier 2+ sources preferred, academic sources
    required for core claims, freshness < 12 months.
    """

    task_class: str = "tech_survey"

    def research_plan(self, query: str, target: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = super().research_plan(query, target)
        plan.update({
            "search_sources": ["academic", "tech", "general"],
            "min_source_tier": 2,
            "require_academic_source": True,
            "max_content_age_months": 12,
        })
        return plan

    def check_claim_decision(self, decision: dict[str, Any]) -> list[ContractCheck]:
        checks = super().check_claim_decision(decision)
        # Gate 5: Cross-reference requirement is stricter for tech surveys
        cross_refs = decision.get("cross_references", [])
        unverified = sum(1 for cr in cross_refs if cr.get("status") == "unverified")
        checks.append(ContractCheck(
            name="cross_reference_tech",
            status="pass" if unverified <= 1 else "needs_revision",
            score=1.0 if unverified == 0 else 0.5,
            blocking_issues=[f"{unverified} unverified claims"] if unverified > 1 else [],
        ))
        return checks
