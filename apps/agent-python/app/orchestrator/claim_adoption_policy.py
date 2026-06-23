"""Map coverage quality and conflicts to claim adoption decisions (S7)."""

from __future__ import annotations

from app.orchestrator.claim_policy_registry import ClaimPolicyView
from app.orchestrator.evidence_scorer import EvidenceScore
from app.schemas.evidence import ClaimType, SourceType
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceConflict, RejectedEvidence


class ClaimAdoptionPolicy:
    def decide(
        self,
        policy: ClaimPolicyView,
        scores: list[EvidenceScore],
        conflicts: list[EvidenceConflict],
        *,
        preferred_id: str | None,
    ) -> tuple[ClaimDecision, list[RejectedEvidence]]:
        quality = self._coverage_quality(policy, scores)
        adopted_ids: list[str] = []
        rejected: list[RejectedEvidence] = []
        limitations: list[str] = []
        supporting_tools: list[str] = []

        if preferred_id:
            adopted_ids.append(preferred_id)
        elif scores:
            adopted_ids.append(scores[0].evidence_id)

        for s in scores:
            if s.evidence_id not in adopted_ids:
                rejected.append(
                    RejectedEvidence(
                        evidence_id=s.evidence_id,
                        claim_type=policy.claim_type,
                        reason="lower rank or conflicting value",
                    )
                )
            else:
                if s.source_name:
                    supporting_tools.append(s.source_name)

        adoption = self._adoption_for_quality(policy, quality, scores, conflicts)
        if policy.claim_type == "ticket_price":
            adoption = self._ticket_price_adoption(scores, quality, adoption)
        if policy.requires_exact_fact and any(
            (s.source_type or "").lower() == "model_prior" for s in scores if s.evidence_id in adopted_ids
        ):
            adoption = "refuse_to_guess"
            limitations.append("模型先验不能作为精确事实依据。")

        confidence = scores[0].total_score if scores else 0.0
        if conflicts:
            confidence = max(0.2, confidence - 0.15)
            limitations.append(conflicts[0].conflict_note)

        reason = f"coverage={quality}, adoption={adoption}, tier={policy.policy_tier}"
        if quality == "none" and policy.priority == "optional":
            adoption = "omit"

        return (
            ClaimDecision(
                claim_type=policy.claim_type,
                claim_family=policy.claim_family,
                claim_description=policy.claim_description,
                required=policy.priority == "required",
                coverage_quality=quality,
                adoption=adoption,
                adopted_evidence_ids=adopted_ids if adoption not in {"omit", "refuse_to_guess", "ask_clarification"} else [],
                rejected_evidence_ids=[r.evidence_id for r in rejected],
                supporting_tool_names=list(dict.fromkeys(supporting_tools))[:5],
                confidence=round(confidence, 3),
                reason=reason,
                limitations=limitations,
            ),
            rejected,
        )

    def _coverage_quality(self, policy: ClaimPolicyView, scores: list[EvidenceScore]) -> str:
        if not scores:
            return "none"
        top = scores[0]
        if top.total_score >= 0.72 and top.source_reliability >= 0.85:
            return "strong"
        if top.total_score >= 0.55:
            return "partial"
        if top.total_score >= 0.35:
            return "weak"
        return "none"

    def _adoption_for_quality(
        self,
        policy: ClaimPolicyView,
        quality: str,
        scores: list[EvidenceScore],
        conflicts: list[EvidenceConflict],
    ) -> str:
        if quality == "none":
            return self._missing_adoption(policy)
        if quality == "weak":
            if policy.missing_behavior == "ask_clarification":
                return "ask_clarification"
            return "adopt_with_limitation"
        if quality == "partial":
            if conflicts:
                return "adopt_with_limitation"
            return "adopt_with_limitation" if policy.requires_exact_fact else "adopt"
        if conflicts and policy.requires_exact_fact:
            return "adopt_with_limitation"
        return "adopt"

    @staticmethod
    def _missing_adoption(policy: ClaimPolicyView) -> str:
        behavior = policy.missing_behavior
        if behavior == "ask_clarification":
            return "ask_clarification"
        if behavior == "omit_claim":
            return "omit"
        if behavior == "refuse_to_guess":
            return "refuse_to_guess"
        return "adopt_with_limitation"

    @staticmethod
    def _ticket_price_adoption(scores: list[EvidenceScore], quality: str, current: str) -> str:
        if not scores:
            return "refuse_to_guess"
        top = scores[0]
        ct_values = top.claim_value
        is_candidate = any(
            kw in (top.rank_reason or "").lower() or "candidate" in ct_values.lower()
            for kw in ("ticket_platform", "review")
        )
        if quality != "strong":
            return "candidate_only"
        if top.source_reliability < 0.85:
            return "candidate_only"
        return current if current == "adopt" else "candidate_only"
