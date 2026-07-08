"""NEARBY-task evidence gate: drop obvious junk before merging subagent output into state."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.orchestrator.information_need_aliases import is_nearby_need, query_text_from_state, resolve_nearby_need
from app.orchestrator.s5_poi_anchor_policy import task_requires_mandatory_poi_anchor
from app.schemas.evidence import ClaimType, Evidence, SourceType
from app.schemas.user_query import TravelAgentState

_KEEP_CLAIM_TYPES = frozenset(
    {
        ClaimType.COORDINATES,
        ClaimType.PLACE_CANDIDATES,
        ClaimType.POI_UID,
        ClaimType.FOOD,
        ClaimType.LODGING,
        ClaimType.GENERAL_FACT,
        ClaimType.ADDRESS,
        ClaimType.RATING_CANDIDATE,
        ClaimType.PRICE_CANDIDATE,
    }
)

_PLATFORM_DOMAIN_SUFFIXES = (
    "dianping.com",
    "ctrip.com",
    "meituan.com",
)

_JUNK_DOMAIN_FRAGMENTS = (
    "chsi.com.cn",
    "gaokao",
    "vw.com",
    "autohome",
)

_FOOD_SIGNAL_RE = re.compile(r"餐厅|美食|小吃|饭馆|火锅|烧烤|料理|餐饮|附近.*吃", re.I)


def _coerce_evidence(items: list) -> list[Evidence]:
    out: list[Evidence] = []
    for item in items:
        if isinstance(item, Evidence):
            out.append(item)
        elif isinstance(item, dict):
            out.append(Evidence.model_validate(item))
    return out


def _claim_types(evidence: Evidence) -> set[ClaimType]:
    return {claim.claim_type for claim in evidence.claims}


def _has_keep_claim(evidence: Evidence) -> bool:
    return bool(_claim_types(evidence) & _KEEP_CLAIM_TYPES)


def _only_travel_advice(evidence: Evidence) -> bool:
    types = _claim_types(evidence)
    return bool(types) and types <= {ClaimType.TRAVEL_ADVICE}


def _url_on_platform(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == suffix or host.endswith("." + suffix) for suffix in _PLATFORM_DOMAIN_SUFFIXES)


def _is_junk_url(url: str | None) -> bool:
    if not url:
        return False
    lower = url.lower()
    return any(fragment in lower for fragment in _JUNK_DOMAIN_FRAGMENTS)


def _has_food_signal(evidence: Evidence) -> bool:
    if ClaimType.FOOD in _claim_types(evidence):
        return True
    for claim in evidence.claims:
        text = f"{claim.value or ''} {claim.raw_text or ''}"
        if _FOOD_SIGNAL_RE.search(text):
            return True
    return False


def _reject_reason(
    evidence: Evidence,
    *,
    subagent: str,
    claim_target: str,
) -> str | None:
    canonical = resolve_nearby_need(claim_target)
    is_food_nearby = canonical == "nearby_food"

    if evidence.source_type == SourceType.MAP:
        if is_nearby_need(claim_target) and subagent != "entity_resolution_agent" and _only_travel_advice(evidence):
            return "nearby_gate:map_travel_advice_only"
        return None
    if _has_keep_claim(evidence):
        return None

    url = evidence.source_url
    if _is_junk_url(url):
        return "nearby_gate:junk_domain"

    if evidence.source_type in {SourceType.REVIEW_PLATFORM, SourceType.FOOD_PLATFORM}:
        if not url:
            return "nearby_gate:platform_missing_url"
        if not _url_on_platform(url):
            return "nearby_gate:platform_url_mismatch"
        return None

    if evidence.source_type == SourceType.WEB and is_food_nearby and subagent == "fact_search_agent":
        if _only_travel_advice(evidence):
            return "nearby_gate:search_mcp_travel_advice_only"
        if url and not _url_on_platform(url) and not _has_food_signal(evidence):
            return "nearby_gate:web_no_food_signal"

    return None


def filter_subagent_evidence(
    state: TravelAgentState,
    evidence: list,
    *,
    subagent: str,
    output: dict,
) -> tuple[list[Evidence], list[dict]]:
    """Return (accepted, rejected_meta). No-op unless task is NEARBY-style."""
    if not task_requires_mandatory_poi_anchor(state):
        return _coerce_evidence(evidence), []

    if subagent == "entity_resolution_agent":
        return _coerce_evidence(evidence), []

    items = _coerce_evidence(evidence)
    if not items:
        return [], []

    claim_target = resolve_nearby_need(
        str(output.get("claim_target") or output.get("information_need") or ""),
        text=query_text_from_state(state),
    )

    accepted: list[Evidence] = []
    rejected: list[dict] = []
    for item in items:
        reason = _reject_reason(item, subagent=subagent, claim_target=claim_target)
        if reason:
            rejected.append(
                {
                    "evidence_id": item.evidence_id,
                    "reason": reason,
                    "source_name": item.source_name,
                    "source_url": item.source_url,
                }
            )
        else:
            accepted.append(item)
    return accepted, rejected
