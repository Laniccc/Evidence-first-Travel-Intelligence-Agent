"""Score evidence relevance and reliability for a claim (S7)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.orchestrator.claim_policy_registry import (
    GEO_ONLY_CLAIMS,
    REVIEW_EXPERIENCE_CLAIMS,
    SOURCE_RELIABILITY,
    ClaimPolicyView,
    source_type_key,
)
from app.orchestrator.claim_search_planner import is_search_miss_value
from app.orchestrator.nearby_recommendation_policy import (
    claim_aliases_for_need,
    place_candidates_is_nearby_recommendation,
)
from app.orchestrator.official_source_judgement import (
    OfficialSupportSummary,
    best_official_support,
    official_source_reliability,
    parse_candidate_from_evidence,
)
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.orchestrator.ticket_price_audit import (
    PLATFORM_SOURCE_CLASSES,
    TICKET_CLAIMS,
    evidence_ticket_blob,
    is_platform_addon_for_claim,
)


@dataclass
class EvidenceScore:
    evidence_id: str
    claim_type: str
    source_name: str | None
    source_type: str | None
    claim_value: str
    total_score: float
    source_reliability: float
    claim_relevance: float
    claim_support: float
    freshness: float
    specificity: float
    tool_success: float
    corroboration_bonus: float = 0.0
    conflict_penalty: float = 0.0
    rank_reason: str = ""


class EvidenceScorer:
    def score_claim_evidence(
        self,
        policy: ClaimPolicyView,
        evidence: list,
        *,
        tool_traces: list | None = None,
    ) -> list[EvidenceScore]:
        rows: list[EvidenceScore] = []
        official_support = best_official_support(evidence, policy.claim_type)
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                if not self._is_relevant(policy, claim, ev):
                    continue
                value = str(claim.value)
                if is_search_miss_value(value):
                    continue
                rows.append(
                    self._score_one(policy, ev, claim, tool_traces or [], official_support)
                )
        return sorted(rows, key=lambda r: r.total_score, reverse=True)

    def _is_relevant(self, policy: ClaimPolicyView, claim: Claim, ev: Evidence) -> bool:
        ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
        if ct in policy.irrelevant_claim_types:
            return False
        if policy.claim_type == "ticket_price" and ct in {
            ClaimType.REVIEW_SUMMARY.value,
            ClaimType.REVIEW_ASPECT.value,
        }:
            return False
        if policy.claim_type in TICKET_CLAIMS and ct in {
            ClaimType.OFFICIAL_SOURCE_CANDIDATE.value,
            ClaimType.TICKET_PRICE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            ClaimType.PRICE_CANDIDATE.value,
            ClaimType.ACTIVITY_PRICE.value,
            ClaimType.TICKET_TYPE.value,
        }:
            if not _evidence_has_extractable_ticket_fact(ev, policy.claim_type, claim):
                return False
            source_type = ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type)
            if source_type in PLATFORM_SOURCE_CLASSES and is_platform_addon_for_claim(
                evidence_ticket_blob(ev), claim_type=policy.claim_type
            ):
                return False
        if ct == ClaimType.OFFICIAL_SOURCE_CANDIDATE.value:
            cand = parse_candidate_from_evidence(ev)
            if not cand:
                return False
            rel = float((cand.claim_relevance_hints or {}).get(policy.claim_type, 0.0))
            return rel > 0.15 or policy.claim_type in (cand.supports_claim_types or [])
        if policy.claim_type in REVIEW_EXPERIENCE_CLAIMS:
            if ct in {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value}:
                return False
            if ct in {
                ClaimType.REVIEW_SUMMARY.value,
                ClaimType.REVIEW_ASPECT.value,
                ClaimType.TRAVEL_ADVICE.value,
                ClaimType.TICKET_RELATED_MENTIONS.value,
            }:
                return True
            if policy.claim_type in policy.claim_aliases or ct in policy.claim_aliases:
                return True
            return "review" in ct or "suitability" in policy.claim_type
        if ct in GEO_ONLY_CLAIMS and policy.claim_family != "geo_fact":
            if policy.claim_family == "nearby_recommendation" and ct == ClaimType.PLACE_CANDIDATES.value:
                return place_candidates_is_nearby_recommendation(claim)
            return False
        if policy.claim_family == "nearby_recommendation":
            aliases = claim_aliases_for_need(policy.claim_type)
            if ct in aliases:
                if ct == ClaimType.PLACE_CANDIDATES.value:
                    return place_candidates_is_nearby_recommendation(claim)
                return True
        if policy.claim_type == "elevation" and ct == ClaimType.TRAVEL_ADVICE.value:
            return bool(re.search(r"海拔|高度|\d{3,5}\s*米", str(claim.value), re.I))
        if ct in policy.claim_aliases or policy.claim_type in ct:
            return True
        if policy.claim_type in ct:
            return True
        if policy.policy_tier == "generic":
            return len(str(claim.value)) >= 3
        return False

    def _score_one(
        self,
        policy: ClaimPolicyView,
        ev: Evidence,
        claim: Claim,
        tool_traces: list,
        official_support: OfficialSupportSummary,
    ) -> EvidenceScore:
        src_key = source_type_key(ev.source_type, ev.source_name)
        source_rel = SOURCE_RELIABILITY.get(src_key, 0.45)
        ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
        relevance = 0.9 if ct in policy.claim_aliases else 0.55
        if policy.claim_family == "nearby_recommendation" and ct in claim_aliases_for_need(policy.claim_type):
            relevance = 0.88

        if ct == ClaimType.OFFICIAL_SOURCE_CANDIDATE.value:
            cand = parse_candidate_from_evidence(ev)
            if cand:
                source_rel = official_source_reliability(cand, policy.claim_type)
                relevance = float((cand.claim_relevance_hints or {}).get(policy.claim_type, 0.55))
        elif policy.claim_type == "ticket_price" and ct in {
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            ClaimType.PRICE_CANDIDATE.value,
            ClaimType.TICKET_RELATED_MENTIONS.value,
        }:
            relevance = 0.65
            if official_support.tier in {"none", "weak"}:
                source_rel = min(source_rel, 0.55)
            elif official_support.tier == "partial":
                source_rel = min(source_rel, 0.70)
        elif (
            policy.claim_type == "ticket_price"
            and ct == ClaimType.TICKET_PRICE.value
            and ev.source_type == SourceType.WEB
            and official_support.tier in {"none", "weak"}
        ):
            source_rel = min(source_rel, 0.50)

        support = min(1.0, float(claim.confidence) * float(ev.confidence or 0.5) * 2)
        freshness = 0.8 if (ev.data_freshness and ev.data_freshness.value == "recent") else 0.55
        value = str(claim.value)
        specificity = 0.9 if any(ch.isdigit() for ch in value) or len(value) > 40 else 0.5
        tool_success = 1.0
        for trace in tool_traces:
            if getattr(trace, "evidence_ids", None) and ev.evidence_id in trace.evidence_ids:
                if trace.status != "ok":
                    tool_success = 0.4
        if ev.source_type == SourceType.MODEL_PRIOR and policy.requires_exact_fact:
            source_rel = min(source_rel, 0.25)
            relevance *= 0.3
        total = (
            source_rel * 0.30
            + relevance * 0.25
            + support * 0.20
            + freshness * 0.10
            + specificity * 0.10
            + tool_success * 0.05
        )
        rank_reason = f"{src_key} rel={relevance:.2f}"
        if ct == ClaimType.OFFICIAL_SOURCE_CANDIDATE.value:
            cand = parse_candidate_from_evidence(ev)
            if cand:
                rank_reason = f"official_candidate:{cand.source_class} tier={official_support.tier}"
        return EvidenceScore(
            evidence_id=ev.evidence_id,
            claim_type=policy.claim_type,
            source_name=ev.source_name,
            source_type=ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
            claim_value=value,
            total_score=round(total, 4),
            source_reliability=source_rel,
            claim_relevance=relevance,
            claim_support=support,
            freshness=freshness,
            specificity=specificity,
            tool_success=tool_success,
            rank_reason=rank_reason,
        )


def _evidence_has_extractable_ticket_fact(ev: Evidence, claim_type: str, claim: Claim) -> bool:
    from app.orchestrator.search_snippet_policy import _source_type_label
    from app.orchestrator.ticket_price_extractor import (
        extract_ticket_price_from_evidence,
        extract_ticket_price_from_text,
    )

    source_class = _source_type_label(ev.source_type)
    ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
    if ct == ClaimType.OFFICIAL_SOURCE_CANDIDATE.value:
        cand = parse_candidate_from_evidence(ev)
        if not cand:
            return False
        text = " ".join(
            str(part or "")
            for part in (
                cand.title,
                cand.page_excerpt,
                cand.url,
                claim.raw_text,
                claim.value,
            )
        )
        return (
            extract_ticket_price_from_text(
                text,
                claim_type=claim_type,
                source_url=cand.url,
                source_class="official",
                evidence_strength="partial",
            )
            is not None
        )
    return bool(extract_ticket_price_from_evidence([ev], claim_type=claim_type)) or (
        extract_ticket_price_from_text(
            " ".join(str(part or "") for part in (claim.value, claim.raw_text, claim.normalized_value)),
            claim_type=claim_type,
            source_url=ev.source_url,
            source_class=source_class,
            evidence_strength="partial",
        )
        is not None
    )
