"""Map coverage quality and conflicts to claim adoption decisions (S7)."""

from __future__ import annotations

from app.orchestrator.claim_policy_registry import ClaimPolicyView
from app.orchestrator.evidence_scorer import EvidenceScore
from app.orchestrator.intent_s7_policy import apply_intent_s7_policy
from app.orchestrator.intent_strategy_registry import IntentStrategy
from app.orchestrator.official_source_judgement import best_official_support
from app.schemas.evidence import ClaimType, SourceType
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceConflict, RejectedEvidence
from app.schemas.intent_profile import EvidenceSensitivity


_GEO_ATTRIBUTE_CLAIMS = frozenset({"elevation", "area", "general_fact"})


class ClaimAdoptionPolicy:
    _DECOMP_CLAIM_ALIASES: dict[str, set[str]] = {
        "walking_intensity": {"visit_duration", "walking_intensity", "itinerary_feasibility"},
        "itinerary_feasibility": {"visit_duration", "distance", "itinerary_feasibility", "duration"},
        "transit": {"distance", "transit", "route_plan", "transport_planning"},
        "opening_hours": {"opening_hours"},
    }

    def decide(
        self,
        policy: ClaimPolicyView,
        scores: list[EvidenceScore],
        conflicts: list[EvidenceConflict],
        *,
        preferred_id: str | None,
        evidence: list | None = None,
        fact_decomposition: list | None = None,
        intent_strategy: IntentStrategy | None = None,
    ) -> tuple[ClaimDecision, list[RejectedEvidence]]:
        quality = self._coverage_quality(
            policy, scores, evidence=evidence, fact_decomposition=fact_decomposition
        )
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

        adoption = self._adoption_for_quality(
            policy, quality, scores, conflicts, intent_strategy=intent_strategy
        )
        if intent_strategy and intent_strategy.s7_policy:
            adoption = apply_intent_s7_policy(
                intent_strategy.s7_policy,
                policy,
                quality,
                adoption,
                intent_strategy=intent_strategy,
            )
        if policy.claim_type == "ticket_price":
            adoption = self._ticket_price_adoption(
                scores,
                quality,
                adoption,
                evidence=evidence,
                fact_decomposition=fact_decomposition,
            )
        if policy.claim_type in _GEO_ATTRIBUTE_CLAIMS:
            adoption = self._geo_attribute_adoption(scores, quality, adoption, conflicts)
        if intent_strategy and intent_strategy.evidence_sensitivity == EvidenceSensitivity.HARD_FACT:
            if quality == "partial" and policy.requires_exact_fact:
                adoption = "adopt_with_limitation" if adoption == "adopt" else adoption
                if adoption == "adopt" and conflicts:
                    if policy.claim_type in _GEO_ATTRIBUTE_CLAIMS:
                        adoption = "candidate_only"
                    else:
                        adoption = "refuse_to_guess"
        if intent_strategy and intent_strategy.partial_review_ok and quality == "partial":
            if adoption == "refuse_to_guess":
                adoption = "adopt_with_limitation"
        if intent_strategy and intent_strategy.refuse_asymmetric_comparison and quality == "none":
            adoption = "refuse_to_guess"
        if intent_strategy and intent_strategy.forbid_model_prior_for_live:
            if any(
                (s.source_type or "").lower() == "model_prior" for s in scores if s.evidence_id in adopted_ids
            ):
                adoption = "refuse_to_guess"
                limitations.append("实时问题禁止用模型先验替代现场数据。")
        if policy.requires_exact_fact and any(
            (s.source_type or "").lower() == "model_prior" for s in scores if s.evidence_id in adopted_ids
        ):
            adoption = "refuse_to_guess"
            limitations.append("模型先验不能作为精确事实依据。")

        confidence = scores[0].total_score if scores else 0.0
        if conflicts:
            confidence = max(0.2, confidence - 0.15)
            note = conflicts[0].conflict_note
            if fact_decomposition and self._has_decomposition_for(policy.claim_type, fact_decomposition):
                note = (
                    f"{note} "
                    "已按票种/套餐口径分拆，请在回答中分列呈现而非称价格不确定。"
                )
            limitations.append(note)

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

    def _coverage_quality(
        self,
        policy: ClaimPolicyView,
        scores: list[EvidenceScore],
        *,
        evidence: list | None = None,
        fact_decomposition: list | None = None,
    ) -> str:
        if not scores:
            if fact_decomposition and self._has_decomposition_for(policy.claim_type, fact_decomposition):
                return "partial"
            if evidence and policy.claim_type == "ticket_price":
                support = best_official_support(evidence, policy.claim_type)
                if support.tier == "strong":
                    return "partial"
            return "none"
        top = scores[0]
        quality = "none"
        if top.total_score >= 0.72 and top.source_reliability >= 0.85:
            quality = "strong"
        elif top.total_score >= 0.55:
            quality = "partial"
        elif top.total_score >= 0.35:
            quality = "weak"

        if evidence and policy.claim_type in {"ticket_price", "opening_hours", "seasonal_operation_status"}:
            support = best_official_support(evidence, policy.claim_type)
            if policy.claim_type == "ticket_price":
                if support.tier != "strong":
                    if quality == "strong":
                        quality = "partial"
                    elif support.tier in {"none", "weak"} and quality == "partial":
                        quality = "weak"
                elif support.tier == "strong" and quality in {"partial", "weak"}:
                    quality = "partial"
            elif support.tier == "strong" and quality in {"weak", "none"}:
                quality = "partial"
        if fact_decomposition and self._has_decomposition_for(policy.claim_type, fact_decomposition):
            if quality in {"none", "weak"}:
                quality = "partial"
            elif quality == "partial" and policy.claim_type == "ticket_price":
                quality = "partial"
        if (
            policy.claim_family == "nearby_recommendation"
            and scores
            and quality == "none"
        ):
            quality = "weak"
        return quality

    @staticmethod
    def _has_decomposition_for(claim_type: str, fact_decomposition: list | None) -> bool:
        if not fact_decomposition:
            return False
        allowed = {claim_type, *ClaimAdoptionPolicy._DECOMP_CLAIM_ALIASES.get(claim_type, set())}
        for block in fact_decomposition:
            if not isinstance(block, dict):
                continue
            if block.get("claim_type") not in allowed:
                continue
            items = block.get("items") or []
            if len(items) >= 1:
                return True
        return False

    def _adoption_for_quality(
        self,
        policy: ClaimPolicyView,
        quality: str,
        scores: list[EvidenceScore],
        conflicts: list[EvidenceConflict],
        *,
        intent_strategy: IntentStrategy | None = None,
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
            if intent_strategy and intent_strategy.evidence_sensitivity == EvidenceSensitivity.HARD_FACT:
                return "adopt_with_limitation" if policy.requires_exact_fact else "adopt"
            if intent_strategy and intent_strategy.partial_review_ok:
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
    def _geo_attribute_adoption(
        scores: list[EvidenceScore],
        quality: str,
        current: str,
        conflicts: list[EvidenceConflict],
    ) -> str:
        if not scores:
            return current
        if current in {"refuse_to_guess", "omit", "ask_clarification"} and quality in {
            "weak",
            "partial",
        }:
            return "candidate_only"
        if conflicts and current in {"refuse_to_guess", "adopt"}:
            return "candidate_only"
        return current

    @staticmethod
    def _ticket_price_adoption(
        scores: list[EvidenceScore],
        quality: str,
        current: str,
        *,
        evidence: list | None = None,
        fact_decomposition: list | None = None,
    ) -> str:
        decomposed = ClaimAdoptionPolicy._has_decomposition_for("ticket_price", fact_decomposition)
        if decomposed:
            if current in {"refuse_to_guess", "candidate_only", "omit"}:
                return "adopt_with_limitation"
            if quality in {"none", "weak"}:
                return "adopt_with_limitation"
        if not scores:
            return "refuse_to_guess" if not decomposed else "adopt_with_limitation"
        support = best_official_support(evidence or [], "ticket_price")
        if support.tier != "strong":
            if support.tier == "partial":
                return "candidate_only"
            if support.tier == "weak" and support.best_candidate:
                return "adopt_with_limitation"
            return "candidate_only"
        top = scores[0]
        ct_values = top.claim_value
        if quality != "strong":
            return "candidate_only"
        if top.source_reliability < 0.85:
            return "candidate_only"
        if ClaimType.TICKET_PRICE.value not in ct_values and ClaimType.PRICE_CANDIDATE.value not in (
            top.rank_reason or ""
        ):
            price_claim = any(
                "ticket_price" in (s.rank_reason or "") or any(ch.isdigit() for ch in s.claim_value)
                for s in scores[:3]
            )
            if not price_claim:
                return "adopt_with_limitation"
        return current if current == "adopt" else "candidate_only"
