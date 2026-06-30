"""Ticket-price lookup orchestration helpers — finish, phase gates, limitations."""

from __future__ import annotations

import re

from app.orchestrator.fact_lookup_policy import is_fact_lookup_task, primary_fact_need_from_state
from app.orchestrator.lookup_research_chain import (
    advance_entity_anchor_if_satisfied,
    ensure_lookup_chain_initialized,
    get_lookup_chain,
    mark_phase_complete,
    next_recommended_phase,
    save_lookup_chain,
)
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name
from tools.ticketing.provider_config import is_ticket_provider_tool

_OFFICIAL_TICKET_TOOLS = frozenset(
    {
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "browser_mcp",
    }
)
_PLATFORM_TICKET_TOOLS = frozenset(
    {
        "fliggy_ticket_api_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "baidu_place_detail_mcp",
    }
)
_PLATFORM_PHASES = frozenset(
    {
        "platform_ticket_candidate",
        "ticket_price_extraction",
        "fact_acquisition",
        "retrieval_audit",
    }
)
_TICKET_PRICE_NEEDS = frozenset(
    {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
    }
)
_TICKET_LIMITATION_DROP = re.compile(
    r"天气|同行人|一般游客|游客画像|画像评估|默认近日",
    re.I,
)
_INTERNAL_LIMITATION_DROP = re.compile(
    r"Cannot FINISH|max_steps|configured tools not yet|official_source_discovery_mcp requires|"
    r"policy 拒绝|evidence_planning_and_tool_use reached|ticket platform tool|entity_resolution_agent blocked|"
    r"not allowed in current lookup phase|requires urls or search_results",
    re.I,
)


def filter_user_visible_limitations(limitations: list[str]) -> list[str]:
    return filter_internal_policy_limitations(limitations)


def ticket_lookup_retrieval_complete(state: TravelAgentState) -> bool:
    from app.orchestrator.retrieval_attempt_ledger import retrieval_complete

    return retrieval_complete(state, "ticket_price")


def force_ticket_platform_phase(state: TravelAgentState) -> None:
    """Advance LOOKUP chain to platform_ticket_candidate for ticket platform tools."""
    if not is_fact_lookup_task(state):
        return
    if primary_fact_need_from_state(state) not in _TICKET_PRICE_NEEDS:
        return
    advance_entity_anchor_if_satisfied(state)
    chain = ensure_lookup_chain_initialized(state)
    if "entity_anchor" not in chain.completed_phases:
        mark_phase_complete(state, "entity_anchor")
        chain = get_lookup_chain(state)
    chain.current_phase = "platform_ticket_candidate"
    save_lookup_chain(state, chain)


def apply_ticket_gap_phase_override(state: TravelAgentState, gap) -> bool:
    """When gap-fill suggests platform ticket tools, switch to platform_ticket_candidate."""
    from app.schemas.evidence_gap_request import EvidenceGapRequest

    if isinstance(gap, dict):
        gap = EvidenceGapRequest.model_validate(gap)
    if gap.claim_type not in _TICKET_PRICE_NEEDS:
        return False
    suggested = [resolve_tool_name(t) for t in (gap.suggested_tools or [])]
    if not any(t in _PLATFORM_TICKET_TOOLS or is_ticket_provider_tool(t) for t in suggested):
        return False
    force_ticket_platform_phase(state)
    return True


def ticket_platform_tool_allowed(state: TravelAgentState, tool_name: str) -> bool:
    resolved = resolve_tool_name(tool_name)
    if resolved not in _PLATFORM_TICKET_TOOLS and not is_ticket_provider_tool(resolved):
        return True
    if primary_fact_need_from_state(state) not in _TICKET_PRICE_NEEDS:
        return True
    chain = get_lookup_chain(state)
    current = chain.current_phase
    if current in _PLATFORM_PHASES:
        return True
    if current in {
        "entity_anchor",
        "research_frame",
        "source_plan",
        "official_site_discovery",
        "official_ticket_page_discovery",
        "official_discovery",
    }:
        return False
    phase = next_recommended_phase(state) or current
    return phase in _PLATFORM_PHASES or phase is None


def filter_ticket_price_limitations(limitations: list[str], *, need: str) -> list[str]:
    if need not in _TICKET_PRICE_NEEDS:
        return filter_internal_policy_limitations(limitations)
    kept: list[str] = []
    for line in limitations or []:
        text = str(line or "").strip()
        if not text:
            continue
        if _TICKET_LIMITATION_DROP.search(text) or _INTERNAL_LIMITATION_DROP.search(text):
            continue
        kept.append(text)
    return kept


def filter_internal_policy_limitations(limitations: list[str]) -> list[str]:
    from app.orchestrator.response_sanitizer import sanitize_limitations

    prelim = [
        str(line or "").strip()
        for line in (limitations or [])
        if str(line or "").strip() and not _INTERNAL_LIMITATION_DROP.search(str(line))
    ]
    return sanitize_limitations(prelim, max_items=6)


def is_internal_policy_limitation(message: str) -> bool:
    return bool(_INTERNAL_LIMITATION_DROP.search(str(message or "")))


def baidu_place_search_allowed_for_ticket(state: TravelAgentState) -> bool:
    if primary_fact_need_from_state(state) not in _TICKET_PRICE_NEEDS:
        return True
    chain = get_lookup_chain(state)
    phase = chain.current_phase
    if phase in {
        "platform_ticket_candidate",
        "ticket_price_extraction",
        "official_ticket_page_discovery",
        "retrieval_audit",
    }:
        return False
    from app.orchestrator.lookup_entity_resolution_policy import lookup_entity_anchor_satisfied

    if lookup_entity_anchor_satisfied(state):
        for trace in state.tool_traces or []:
            if resolve_tool_name(str(trace.tool_name or "")) == "baidu_place_search_mcp":
                return False
        structured = state.structured_result or {}
        n = sum(
            1
            for row in (structured.get("subagent_results") or [])
            if row.get("subagent") == "entity_resolution_agent"
        )
        if n >= 1:
            return False
    return True
