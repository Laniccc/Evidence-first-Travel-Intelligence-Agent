"""Evidence strength ladder by claim_family."""

from __future__ import annotations

from app.orchestrator.search_snippet_policy import (
    _source_type_label,
    is_official_page_evidence,
    is_platform_structured_price,
    is_search_snippet_evidence,
)
from app.schemas.evidence import Evidence

_ADOPTION_ORDER = {
    "strong": 5,
    "partial": 4,
    "candidate_only": 3,
    "weak": 2,
    "rejected": 1,
    "no_evidence": 0,
}


def _cap_adoption(level: str, ceiling: str) -> str:
    if _ADOPTION_ORDER.get(level, 0) > _ADOPTION_ORDER.get(ceiling, 0):
        return level
    return ceiling


def ladder_for_family(claim_family: str) -> dict[str, str]:
    if claim_family == "ticket_booking":
        return {
            "official_page": "strong",
            "official_source": "strong",
            "ticket_platform": "partial",
            "search_snippet": "candidate_only",
            "guide": "weak",
            "none": "rejected",
        }
    if claim_family == "operation_status":
        return {
            "official_page": "strong",
            "official_source": "strong",
            "search_snippet_official": "partial",
            "search_snippet": "candidate_only",
            "map": "partial",
            "guide": "weak",
        }
    if claim_family == "geo_fact":
        return {
            "geo_authority": "strong",
            "official": "strong",
            "encyclopedia": "partial",
            "search_snippet": "partial",
            "guide": "weak",
        }
    if claim_family == "rule_policy":
        return {
            "official_page": "strong",
            "official_source": "strong",
            "platform": "partial",
            "search_snippet": "weak",
            "guide": "weak",
        }
    if claim_family == "realtime_notice":
        return {
            "live_api": "strong",
            "official_notice": "strong",
            "news": "partial",
            "search_snippet": "weak",
            "guide": "rejected",
        }
    return {
        "official": "strong",
        "search_snippet": "candidate_only",
        "guide": "weak",
    }


def evidence_bucket(ev: Evidence, claim_family: str) -> str:
    if is_official_page_evidence(ev):
        return "official_page"
    src = str(ev.source_name or "").lower()
    st = _source_type_label(ev.source_type).lower()
    if claim_family == "ticket_booking" and is_platform_structured_price(ev):
        return "ticket_platform"
    if is_search_snippet_evidence(ev):
        if claim_family == "operation_status" and any(
            h in f"{src} {ev.source_url or ''}".lower() for h in (".gov", "dpm.org", "景区", "博物馆")
        ):
            return "search_snippet_official"
        return "search_snippet"
    if st in {"map", "places"} or "baidu_place" in src:
        return "map"
    if st in {"official", "government", "tourism_board"}:
        return "official_source"
    if claim_family == "geo_fact" and any(h in src for h in ("wikidata", "wikipedia", "osm")):
        return "geo_authority"
    if any(h in src for h in ("攻略", "游记", "review", "点评")):
        return "guide"
    return "none"


def strength_for_evidence(ev: Evidence, claim_family: str) -> str:
    ladder = ladder_for_family(claim_family)
    bucket = evidence_bucket(ev, claim_family)
    return ladder.get(bucket, ladder.get("none", "weak"))


def max_adoption_for_evidence(ev: Evidence, claim_family: str) -> str:
    return strength_for_evidence(ev, claim_family)
