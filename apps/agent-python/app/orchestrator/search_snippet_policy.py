"""Classify search-snippet vs page-read evidence strength for hard-fact claims."""

from __future__ import annotations

import re

from app.schemas.evidence import ClaimType, Evidence, SourceType

_SEARCH_SOURCE_HINTS = frozenset(
    {"search", "search_mcp", "open-websearch", "websearch", "keyword_search"}
)
_PLATFORM_TOOLS = frozenset(
    {
        "fliggy",
        "ctrip",
        "dianping",
        "ticketlens",
        "飞猪",
        "携程",
        "点评",
    }
)
_THIRD_PARTY_SNIPPET_HINTS = re.compile(
    r"旅行社|攻略|游记|ota|团购|第三方|摘要",
    re.I,
)


def is_search_snippet_evidence(ev: Evidence) -> bool:
    src = str(ev.source_name or "").lower()
    st = str(ev.source_type or "").lower()
    if st in {SourceType.WEB.value, "web", "search_snippet"}:
        if any(h in src for h in _SEARCH_SOURCE_HINTS):
            return True
    if any(h in src for h in _SEARCH_SOURCE_HINTS):
        return True
    for claim in ev.claims or []:
        ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
        if ct in {ClaimType.TRAVEL_ADVICE.value, ClaimType.GENERAL_FACT.value}:
            if any(h in src for h in _SEARCH_SOURCE_HINTS):
                return True
    return False


def is_platform_structured_price(ev: Evidence) -> bool:
    src = str(ev.source_name or "").lower()
    if not any(p in src for p in _PLATFORM_TOOLS):
        return False
    for claim in ev.claims or []:
        ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
        if ct in {
            ClaimType.TICKET_PRICE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            ClaimType.PRICE_CANDIDATE.value,
        }:
            return True
    return False


def _source_type_label(source_type) -> str:
    if source_type is None:
        return "unknown"
    if hasattr(source_type, "value"):
        return str(source_type.value)
    return str(source_type)


def is_official_page_evidence(ev: Evidence) -> bool:
    from tools.official_source.url_normalizer import is_third_party_platform_url
    from app.orchestrator.official_source_judgement import parse_candidate_from_evidence

    if parse_candidate_from_evidence(ev) is not None:
        return False
    if is_third_party_platform_url(str(ev.source_url or "")):
        return False
    st = _source_type_label(ev.source_type).lower()
    if st in {"official", "official_page", "government", "tourism_board"}:
        return True
    src = str(ev.source_name or "").lower()
    return "official_page_reader" in src or "official_source" in src or "official page" in src


def evidence_strength_for_claim(ev: Evidence, claim_type: str) -> str:
    """Return strong | partial | candidate_only | weak | reject."""
    from app.orchestrator.claim_family_registry import claim_family_for_type
    from app.orchestrator.evidence_ladder import strength_for_evidence

    family = claim_family_for_type(claim_type)
    ladder_strength = strength_for_evidence(ev, family)
    if ladder_strength != "weak":
        return ladder_strength
    if is_official_page_evidence(ev):
        return "strong"
    if claim_type == "ticket_price":
        if is_platform_structured_price(ev):
            return "partial"
        if is_search_snippet_evidence(ev):
            blob = " ".join(str(c.value or "") for c in (ev.claims or []))
            if _THIRD_PARTY_SNIPPET_HINTS.search(blob) or _THIRD_PARTY_SNIPPET_HINTS.search(
                str(ev.source_name or "")
            ):
                return "candidate_only"
            return "candidate_only"
    if claim_type == "opening_hours":
        if is_search_snippet_evidence(ev):
            return "partial"
    if is_search_snippet_evidence(ev):
        return "candidate_only"
    return "weak"


def can_support_strong_adoption(ev: Evidence, claim_type: str) -> bool:
    return evidence_strength_for_claim(ev, claim_type) == "strong"


def can_be_direct_answer(ev: Evidence, claim_type: str) -> bool:
    strength = evidence_strength_for_claim(ev, claim_type)
    return strength in {"strong", "partial"}
