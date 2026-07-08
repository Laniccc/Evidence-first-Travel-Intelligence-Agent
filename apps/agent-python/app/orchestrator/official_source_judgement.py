"""S7 official source candidate judgement."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.evidence import ClaimType, Evidence
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.official_source import (
    OfficialSourceCandidate,
    SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE,
    SOURCE_CLASS_MAP_PROVIDER_CANDIDATE,
    SOURCE_CLASS_NOT_OFFICIAL,
    SOURCE_CLASS_OFFICIAL_GOVERNMENT,
    SOURCE_CLASS_OTA_PLATFORM,
    SOURCE_CLASS_REVIEW_PLATFORM,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE,
    SOURCE_CLASS_SEO_CONTENT_SITE,
    SOURCE_CLASS_THIRD_PARTY_PLATFORM,
    SOURCE_CLASS_TOURISM_BOARD_OFFICIAL,
    STRONG_OFFICIAL_SOURCE_CLASSES,
)

SOURCE_CLASS_BASE_WEIGHT: dict[str, float] = {
    SOURCE_CLASS_OFFICIAL_GOVERNMENT: 0.95,
    SOURCE_CLASS_TOURISM_BOARD_OFFICIAL: 0.92,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL: 0.90,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE: 0.72,
    "official_account_candidate": 0.68,
    SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE: 0.55,
    SOURCE_CLASS_MAP_PROVIDER_CANDIDATE: 0.50,
    SOURCE_CLASS_REVIEW_PLATFORM: 0.45,
    SOURCE_CLASS_OTA_PLATFORM: 0.40,
    SOURCE_CLASS_THIRD_PARTY_PLATFORM: 0.35,
    SOURCE_CLASS_SEO_CONTENT_SITE: 0.25,
    SOURCE_CLASS_NOT_OFFICIAL: 0.15,
    "unknown": 0.30,
}

_OFFICIAL_STRONG_CLASSES = STRONG_OFFICIAL_SOURCE_CLASSES


@dataclass
class JudgementResult:
    coverage_tier: str
    reason: str
    candidate: OfficialSourceCandidate | None = None


@dataclass
class OfficialSupportSummary:
    tier: str
    best_candidate: OfficialSourceCandidate | None
    reason: str
    evidence_id: str | None = None


def parse_candidate_from_evidence(ev: Evidence) -> OfficialSourceCandidate | None:
    for claim in ev.claims:
        ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
        if ct != ClaimType.OFFICIAL_SOURCE_CANDIDATE.value:
            continue
        nv = claim.normalized_value
        if isinstance(nv, dict) and nv.get("source_class"):
            return OfficialSourceCandidate.model_validate(nv)
        if isinstance(nv, OfficialSourceCandidate):
            return nv
    return None


def iter_official_candidates(evidence: list) -> list[tuple[str, OfficialSourceCandidate]]:
    out: list[tuple[str, OfficialSourceCandidate]] = []
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        cand = parse_candidate_from_evidence(ev)
        if cand and cand.source_class not in {SOURCE_CLASS_NOT_OFFICIAL, "unknown"}:
            out.append((ev.evidence_id, cand))
    return out


def judge_candidate_for_claim(
    candidate: OfficialSourceCandidate,
    claim_type: str,
) -> JudgementResult:
    sc = candidate.source_class
    hints = candidate.claim_relevance_hints or {}
    rel = float(hints.get(claim_type, 0.0))

    if claim_type == "review_signal":
        if sc in {SOURCE_CLASS_REVIEW_PLATFORM, SOURCE_CLASS_OTA_PLATFORM}:
            return JudgementResult("partial", "review/OTA platform for review_signal", candidate)
        return JudgementResult("none", "official source not used for review_signal", candidate)

    if claim_type == "ticket_price":
        if sc in _OFFICIAL_STRONG_CLASSES and candidate.has_ticket_info:
            return JudgementResult("strong", f"{sc} with ticket info", candidate)
        if sc in _OFFICIAL_STRONG_CLASSES and not candidate.has_ticket_info:
            return JudgementResult("weak", f"{sc} background without ticket price", candidate)
        if sc == SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE and candidate.has_ticket_info:
            return JudgementResult("partial", "scenic operator candidate with ticket signal", candidate)
        if sc == SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE and candidate.has_ticket_info:
            return JudgementResult("partial", "authorized platform with ticket signal", candidate)
        if sc in {SOURCE_CLASS_OTA_PLATFORM, SOURCE_CLASS_REVIEW_PLATFORM, SOURCE_CLASS_SEO_CONTENT_SITE}:
            return JudgementResult("weak", "platform/guide content for ticket_price", candidate)
        if rel >= 0.5 and candidate.has_ticket_info:
            return JudgementResult("partial", "ticket signal from non-strong official class", candidate)
        return JudgementResult("none", "no qualifying official ticket support", candidate)

    if claim_type == "opening_hours":
        if sc in _OFFICIAL_STRONG_CLASSES | {SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE} and candidate.has_opening_hours:
            tier = "strong" if sc in _OFFICIAL_STRONG_CLASSES else "partial"
            return JudgementResult(tier, f"{sc} with opening hours", candidate)
        if sc in {SOURCE_CLASS_MAP_PROVIDER_CANDIDATE, SOURCE_CLASS_OTA_PLATFORM} and candidate.has_opening_hours:
            return JudgementResult("partial", "map/OTA hours candidate", candidate)
        return JudgementResult("none", "no opening hours signal", candidate)

    if claim_type in {"seasonal_operation_status", "road_opening_period", "temporary_closure"}:
        if sc in _OFFICIAL_STRONG_CLASSES and candidate.has_notice_info:
            return JudgementResult("strong", f"{sc} with notice/closure info", candidate)
        if sc in {SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL, SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE} and candidate.has_notice_info:
            return JudgementResult("partial", "scenic operator notice candidate", candidate)
        if sc in {SOURCE_CLASS_THIRD_PARTY_PLATFORM, SOURCE_CLASS_SEO_CONTENT_SITE}:
            return JudgementResult("weak", "third-party or guide content", candidate)
        return JudgementResult("none", "no official notice support", candidate)

    if claim_type == "destination_background":
        if sc in {SOURCE_CLASS_OFFICIAL_GOVERNMENT, SOURCE_CLASS_TOURISM_BOARD_OFFICIAL}:
            return JudgementResult("strong", "government/tourism heritage page", candidate)
        if sc in {SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL, SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE}:
            return JudgementResult("partial", "scenic operator intro page", candidate)
        if sc == SOURCE_CLASS_SEO_CONTENT_SITE:
            return JudgementResult("weak", "travel guide content", candidate)
        return JudgementResult("none", "no destination background support", candidate)

    if rel >= 0.7:
        return JudgementResult("partial", f"claim relevance {rel:.2f}", candidate)
    if rel >= 0.4:
        return JudgementResult("weak", f"low claim relevance {rel:.2f}", candidate)
    return JudgementResult("none", "no relevance for claim", candidate)


def best_official_support(evidence: list, claim_type: str) -> OfficialSupportSummary:
    best_tier = "none"
    best: OfficialSourceCandidate | None = None
    best_id: str | None = None
    best_reason = "no official source candidates"
    rank = {"none": 0, "weak": 1, "partial": 2, "strong": 3}

    for ev_id, cand in iter_official_candidates(evidence):
        result = judge_candidate_for_claim(cand, claim_type)
        if rank.get(result.coverage_tier, 0) > rank.get(best_tier, 0):
            best_tier = result.coverage_tier
            best = cand
            best_id = ev_id
            best_reason = result.reason
        elif result.coverage_tier == best_tier and cand.official_confidence > (best.official_confidence if best else 0):
            best = cand
            best_id = ev_id
            best_reason = result.reason

    return OfficialSupportSummary(
        tier=best_tier,
        best_candidate=best,
        reason=best_reason,
        evidence_id=best_id,
    )


def official_source_reliability(candidate: OfficialSourceCandidate, claim_type: str) -> float:
    base = SOURCE_CLASS_BASE_WEIGHT.get(candidate.source_class, 0.30)
    rel = float((candidate.claim_relevance_hints or {}).get(claim_type, 0.0))
    if rel <= 0:
        judgement = judge_candidate_for_claim(candidate, claim_type)
        rel = {"strong": 0.9, "partial": 0.65, "weak": 0.35, "none": 0.0}.get(judgement.coverage_tier, 0.0)
    return round(base * max(rel, 0.1 if judgement_tier_positive(candidate, claim_type) else 0.0), 4)


def judgement_tier_positive(candidate: OfficialSourceCandidate, claim_type: str) -> bool:
    return judge_candidate_for_claim(candidate, claim_type).coverage_tier != "none"


def needs_official_source_gap(
    evidence: list,
    claim_type: str,
    decision: ClaimDecision,
) -> bool:
    if claim_type not in {
        "ticket_price",
        "opening_hours",
        "seasonal_operation_status",
        "road_opening_period",
        "temporary_closure",
        "reservation_policy",
    }:
        return False
    if decision.adoption in {"adopt", "adopt_with_limitation"} and decision.coverage_quality == "strong":
        return False

    support = best_official_support(evidence, claim_type)
    if claim_type == "ticket_price":
        if support.tier == "strong":
            return False
        if decision.adoption == "candidate_only":
            return True
        if support.tier in {"none", "weak"}:
            return True
        if support.tier == "partial" and decision.coverage_quality != "strong":
            return True
        return False

    if support.tier in {"none", "weak"} and decision.coverage_quality in {"none", "weak"}:
        return True
    return decision.coverage_quality == "none"


def source_class_priority(source_class: str) -> int:
    order = [
        SOURCE_CLASS_OFFICIAL_GOVERNMENT,
        SOURCE_CLASS_TOURISM_BOARD_OFFICIAL,
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE,
        SOURCE_CLASS_AUTHORIZED_PLATFORM_CANDIDATE,
        SOURCE_CLASS_MAP_PROVIDER_CANDIDATE,
        SOURCE_CLASS_OTA_PLATFORM,
        SOURCE_CLASS_REVIEW_PLATFORM,
        SOURCE_CLASS_THIRD_PARTY_PLATFORM,
        SOURCE_CLASS_SEO_CONTENT_SITE,
        SOURCE_CLASS_NOT_OFFICIAL,
    ]
    try:
        return order.index(source_class)
    except ValueError:
        return 50
