"""Policy helpers for strict_fact_lookup (ticket, hours, elevation, …)."""

from __future__ import annotations

import re

from app.orchestrator.claim_policy_registry import CLAIM_TYPE_ALIASES
from app.orchestrator.fact_lookup_anchor_policy import (
    GEO_FACT_NEEDS,
    interpret_place_for_fact_need,
    is_geographic_fact_need,
    resolved_place_label,
)
from app.orchestrator.information_need_aliases import query_text_from_state
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.semantic_frame import DecisionType, TaskFamily
from app.schemas.user_query import TravelAgentState

HARD_FACT_NEEDS = frozenset(
    {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
        "opening_hours",
        "reservation_policy",
        "seasonal_operation_status",
        "temporary_closure",
        "elevation",
        "highest_peak_elevation",
        "general_fact",
    }
)

_TICKET_CLAIM_TYPES = frozenset(
    {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
    }
)

_FACT_NEED_LABELS = {
    "ticket_price": "门票价格",
    "entrance_ticket_price": "景区门票价格",
    "boat_ticket_price": "游船船票价格",
    "shuttle_bus_ticket_price": "区间车票价",
    "cable_car_ticket_price": "索道/缆车票价",
    "opening_hours": "开放时间",
    "reservation_policy": "预约政策",
    "seasonal_operation_status": "开放状态",
    "temporary_closure": "临时闭园",
    "elevation": "海拔",
    "general_fact": "关键事实",
}

_OFFICIAL_SOURCE_HINTS = re.compile(r"官方|gov|景区|博物馆|文旅|预约|ticket|booking", re.I)
_GEO_AUTHORITY_HINTS = re.compile(
    r"wikidata|wikipedia|openstreetmap|osm|百度百科|baike\.baidu|国家地理|自然资源",
    re.I,
)


def is_ticket_claim_type(claim_type: str | None) -> bool:
    return str(claim_type or "").strip() in _TICKET_CLAIM_TYPES


def is_hard_fact_need(need: str | None) -> bool:
    return str(need or "").strip() in HARD_FACT_NEEDS


def is_fact_lookup_task(state: TravelAgentState) -> bool:
    strategy = state.intent_strategy
    if strategy and strategy.retrieval_mode == "strict_fact_lookup":
        return True
    if strategy and strategy.primary_intent == PrimaryIntent.LOOKUP:
        return True
    frame = state.semantic_frame
    if frame:
        if frame.task_family == TaskFamily.FACT_LOOKUP or frame.decision_type == DecisionType.FACT_LOOKUP:
            return True
        if frame.requires_exact_fact:
            return True
        if frame.information_needs and any(is_hard_fact_need(n) for n in frame.information_needs):
            return True
    contract = state.response_contract
    if contract:
        for req in contract.claim_requirements:
            if is_hard_fact_need(req.claim_type) or req.requires_exact_fact:
                return True
    return False


def primary_fact_need_from_state(state: TravelAgentState) -> str:
    from app.orchestrator.claim_compiler import primary_lookup_claim

    primary = primary_lookup_claim(state)
    if primary and is_hard_fact_need(primary.claim_type):
        return primary.claim_type
    contract = state.response_contract
    if contract:
        for req in contract.claim_requirements:
            if is_hard_fact_need(req.claim_type):
                return req.claim_type
    frame = state.semantic_frame
    if frame and frame.information_needs:
        for need in frame.information_needs:
            if is_hard_fact_need(need):
                return need
    text = query_text_from_state(state)
    if "门票" in text or "票价" in text or "多少钱" in text:
        return "ticket_price"
    if "开放" in text or "营业时间" in text or "几点" in text:
        return "opening_hours"
    if "海拔" in text:
        return "elevation"
    if "预约" in text:
        return "reservation_policy"
    return "general_fact"


def fact_need_label(need: str, state: TravelAgentState | None = None) -> str:
    if need == "ticket_price" and state is not None:
        from app.orchestrator.ticket_product_policy import ensure_ticket_product_context

        ctx = ensure_ticket_product_context(state)
        if ctx and ctx.get("ticket_product") == "boat_ticket":
            return "游船船票价格"
    return _FACT_NEED_LABELS.get(need, need.replace("_", " "))


def focus_claim_types_for_need(need: str) -> frozenset[str]:
    aliases = CLAIM_TYPE_ALIASES.get(need)
    if is_ticket_claim_type(need):
        base = set(_TICKET_CLAIM_TYPES)
        if aliases:
            base.update(aliases)
        base.update(
            {
                ClaimType.TICKET_PRICE.value,
                ClaimType.TICKET_PRICE_CANDIDATE.value,
                ClaimType.PRICE_CANDIDATE.value,
            }
        )
        return frozenset(base)
    if is_geographic_fact_need(need):
        return frozenset(
            {
                need,
                ClaimType.ELEVATION.value,
                ClaimType.GENERAL_FACT.value,
                ClaimType.TRAVEL_ADVICE.value,
            }
        )
    if aliases:
        return aliases
    return frozenset({need})


def _claim_matches_need(claim: Claim, need: str) -> bool:
    ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
    focus = focus_claim_types_for_need(need)
    return ct in focus


def is_authoritative_geo_evidence(ev: Evidence) -> bool:
    from app.orchestrator.peak_elevation_extraction import classify_elevation_text

    has_elevation_claim = False
    for claim in ev.claims or []:
        if not _claim_matches_need(claim, "elevation"):
            continue
        text = f"{getattr(claim, 'value', '')} {getattr(claim, 'raw_text', '')}".strip()
        if classify_elevation_text(text) not in {"none", "unrelated_geo"}:
            has_elevation_claim = True
            break
    if not has_elevation_claim:
        return False
    name = str(ev.source_name or "")
    url = str(ev.source_url or "")
    st = str(ev.source_type or "").lower()
    if st in {"wikidata", "wikipedia", "osm", "encyclopedia"}:
        return True
    return bool(_GEO_AUTHORITY_HINTS.search(name) or _GEO_AUTHORITY_HINTS.search(url))


def has_authoritative_geo_evidence(evidence: list, need: str) -> bool:
    if not is_geographic_fact_need(need):
        return False
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if not is_authoritative_geo_evidence(ev):
            continue
        for claim in ev.claims:
            if _claim_matches_need(claim, need):
                return True
    return False


def is_official_evidence(ev: Evidence) -> bool:
    st = str(ev.source_type or "").lower()
    if st in {SourceType.OFFICIAL.value, "official", "government"}:
        return True
    name = str(ev.source_name or "")
    url = str(ev.source_url or "")
    return bool(_OFFICIAL_SOURCE_HINTS.search(name) or _OFFICIAL_SOURCE_HINTS.search(url))


def count_actionable_fact_claims(evidence: list, need: str) -> int:
    focus = focus_claim_types_for_need(need)
    n = 0
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct not in focus:
                continue
            val = str(claim.value or "").strip()
            if val and val not in {"[]", "{}"}:
                n += 1
    return n


def has_official_fact_evidence(evidence: list, need: str) -> bool:
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if not is_official_evidence(ev):
            continue
        for claim in ev.claims:
            if _claim_matches_need(claim, need):
                return True
    return False


def collect_fact_clues(state: TravelAgentState, *, limit: int = 8) -> list[dict]:
    """Structured fact rows for S8 fact_lookup_guided."""
    from app.orchestrator.fact_lookup_anchor_policy import elevation_clue_rank

    need = primary_fact_need_from_state(state)
    focus = focus_claim_types_for_need(need)
    place = resolved_place_label(state)
    clues: list[dict] = []
    seen: set[str] = set()

    for ev in state.evidence or []:
        if not isinstance(ev, Evidence):
            continue
        from app.orchestrator.evidence_usage_role import is_entity_anchor_only

        if is_entity_anchor_only(ev, need):
            continue
        if is_ticket_claim_type(need):
            from app.orchestrator.ticket_lookup_helpers import is_ticket_price_noise_evidence
            from app.orchestrator.ticket_relevance_policy import ticket_relevance_score
            from tools.ticket_price_text import has_explicit_ticket_price_signal

            if is_ticket_price_noise_evidence(ev):
                continue
            official_source = is_official_evidence(ev)
            blob = ""
            for c in ev.claims:
                if c.claim_type.value in focus:
                    blob = str(c.value or "")
                    break
            if (
                blob
                and not official_source
                and ticket_relevance_score(state, "ticket_price", blob, source_name=str(ev.source_name or "")) < 0.5
            ):
                continue
            if blob and not has_explicit_ticket_price_signal(blob):
                continue
        for claim in ev.claims:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct not in focus:
                continue
            val = str(claim.value or "").strip()
            if is_geographic_fact_need(need):
                from app.orchestrator.peak_elevation_extraction import classify_elevation_text

                if classify_elevation_text(val) in {"none", "unrelated_geo"}:
                    continue
            if is_ticket_claim_type(need):
                if not has_explicit_ticket_price_signal(val):
                    continue
                if (
                    not official_source
                    and ticket_relevance_score(
                        state,
                        ct,
                        val,
                        source_name=str(ev.source_name or ""),
                        source_url=str(ev.source_url or ""),
                    )
                    < 0.5
                ):
                    continue
            if not val or val in seen:
                continue
            seen.add(val)
            official = is_official_evidence(ev)
            auth_geo = is_authoritative_geo_evidence(ev)
            clues.append(
                {
                    "text": val,
                    "claim_type": ct,
                    "information_need": need,
                    "place_name": place,
                    "evidence_id": ev.evidence_id,
                    "source_name": ev.source_name or "",
                    "source_url": ev.source_url or "",
                    "official": official,
                    "authoritative_geo": auth_geo,
                    "confidence": float(getattr(claim, "confidence", None) or ev.confidence or 0.5),
                    "_rank": elevation_clue_rank(val, authoritative_geo=auth_geo, official=official)
                    if is_geographic_fact_need(need)
                    else (20 if official else 0),
                }
            )

    if is_geographic_fact_need(need):
        clues.sort(key=lambda row: (-int(row.get("_rank") or 0), -float(row.get("confidence") or 0)))
    else:
        clues.sort(key=lambda row: (-int(row.get("official") or 0), -float(row.get("confidence") or 0)))

    trimmed: list[dict] = []
    for row in clues[:limit]:
        trimmed.append({k: v for k, v in row.items() if k != "_rank"})
    return trimmed


def _place_label(state: TravelAgentState) -> str:
    return resolved_place_label(state)


def pipeline_search_queries(state: TravelAgentState, need: str) -> list[str]:
    from app.orchestrator.lookup_query_objectives import (
        build_lookup_query_objectives,
        objective_to_search_query,
    )
    from app.orchestrator.lookup_research_chain import ensure_lookup_chain_initialized
    from app.schemas.lookup_research_chain import SourceFamily

    ensure_lookup_chain_initialized(state)
    families: list[SourceFamily] = ["official_operator", "web_reference"]
    if need == "elevation":
        families = ["geo_authority", "official_operator", "web_reference"]
    elif is_ticket_claim_type(need):
        from app.orchestrator.ticket_price_query_ladder import escalation_queries_flat

        ladder = escalation_queries_flat(state, max_queries=12)
        if ladder:
            return ladder[:8]
        families = ["official_operator", "web_reference", "ticket_platform"]
    per_family = 4 if is_ticket_claim_type(need) else 1
    queries: list[str] = []
    for family in families:
        for obj in build_lookup_query_objectives(state, need, family, max_objectives=per_family):
            queries.append(objective_to_search_query(obj))
    if queries:
        return queries[:8] if is_ticket_claim_type(need) else queries[:4]
    place = interpret_place_for_fact_need(_place_label(state), need)
    return [f"{place} {fact_need_label(need)}"]


def pipeline_search_query(state: TravelAgentState, need: str) -> str:
    return pipeline_search_queries(state, need)[0]
