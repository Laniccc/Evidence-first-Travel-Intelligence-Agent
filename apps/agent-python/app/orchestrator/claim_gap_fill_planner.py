"""Gap-fill tool ordering by claim source-family plan."""

from __future__ import annotations

from app.orchestrator.claim_tool_policy import filter_allowed_tools, policy_for_claim
from app.orchestrator.official_chain_policy import (
    can_call_official_discovery,
    can_call_official_page_reader,
)
from app.orchestrator.ticket_lookup_helpers import TICKET_GAP_FILL_TOOLS
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name

_OPENING_HOURS_GAP_TOOLS: list[str] = [
    "search_mcp",
    "official_source_discovery_mcp",
    "official_page_reader_mcp",
    "browser_mcp",
    "baidu_place_detail_mcp",
    "baidu_place_search_mcp",
]

_SEARCH_FIRST = frozenset({"search_mcp", "keyword_search_agent", "fact_search_agent"})
_OFFICIAL_DISCOVERY = frozenset({"official_source_discovery_mcp", "official"})
_OFFICIAL_PAGE = frozenset({"official_page_reader_mcp", "browser_mcp"})
_PLATFORM = frozenset(
    {
        "fliggy_ticket_api_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
    }
)


def gap_tools_for_claim(claim_type: str) -> list[str]:
    if claim_type in {"ticket_price", "entrance_ticket_price", "boat_ticket_price", "shuttle_bus_ticket_price", "cable_car_ticket_price"}:
        return list(TICKET_GAP_FILL_TOOLS)
    if claim_type == "opening_hours":
        return list(_OPENING_HOURS_GAP_TOOLS)
    pol = policy_for_claim(claim_type)
    if pol:
        return list(pol.primary_tools)
    return ["search_mcp"]


def order_gap_tools(
    state: TravelAgentState,
    tools: list[str],
    *,
    claim_type: str,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    claim = claim_type or "general_fact"
    required = gap_tools_for_claim(claim)
    if allowed is not None:
        required = [t for t in required if resolve_tool_name(t) in allowed]
    pool = list(tools or []) + required
    pool = filter_allowed_tools(pool, [claim])
    if claim == "ticket_price" or claim in {
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
    }:
        return _order_ticket_gap(state, pool, claim_type=claim, allowed=allowed)
    if claim == "opening_hours":
        return _order_opening_hours_gap(state, pool, allowed=allowed)
    ordered = _dedupe(pool)
    if allowed is not None:
        ordered = [t for t in ordered if t in allowed]
    return ordered


def _order_ticket_gap(
    state: TravelAgentState,
    tools: list[str],
    *,
    claim_type: str = "ticket_price",
    allowed: frozenset[str] | None = None,
) -> list[str]:
    required = gap_tools_for_claim(claim_type)
    if allowed is not None:
        required = [t for t in required if resolve_tool_name(t) in allowed]
    merged = _dedupe([*(tools or []), *required])
    has_urls = can_call_official_discovery(state, claim_type)
    search_bucket: list[str] = []
    official_disc: list[str] = []
    official_page: list[str] = []
    platform: list[str] = []
    rest: list[str] = []
    for t in merged:
        r = resolve_tool_name(t)
        if r in _SEARCH_FIRST:
            (search_bucket if not has_urls else rest).append(t)
        elif r in _OFFICIAL_DISCOVERY:
            (official_disc if has_urls else rest).append(t)
        elif r in _OFFICIAL_PAGE:
            official_page.append(t)
        elif r in _PLATFORM:
            platform.append(t)
        else:
            rest.append(t)
    if not has_urls and not search_bucket:
        if allowed is None or "search_mcp" in allowed:
            search_bucket = ["search_mcp"]
    ordered = _dedupe([*search_bucket, *official_disc, *official_page, *platform, *rest])
    if allowed is not None:
        ordered = [t for t in ordered if t in allowed]
    return ordered


def _order_opening_hours_gap(
    state: TravelAgentState,
    tools: list[str],
    *,
    allowed: frozenset[str] | None = None,
) -> list[str]:
    has_urls = can_call_official_discovery(state, "opening_hours")
    has_official = can_call_official_page_reader(state, "opening_hours")
    search_bucket: list[str] = []
    official_disc: list[str] = []
    official_page: list[str] = []
    rest: list[str] = []
    for t in tools:
        r = resolve_tool_name(t)
        if r in _SEARCH_FIRST:
            (search_bucket if not has_urls else rest).append(t)
        elif r in _OFFICIAL_DISCOVERY:
            (official_disc if has_urls else rest).append(t)
        elif r in _OFFICIAL_PAGE:
            (official_page if has_official or has_urls else rest).append(t)
        else:
            rest.append(t)
    if not has_urls and not search_bucket:
        if allowed is None or "search_mcp" in allowed:
            search_bucket = ["search_mcp"]
    ordered = _dedupe([*search_bucket, *official_disc, *official_page, *rest])
    if allowed is not None:
        ordered = [t for t in ordered if t in allowed]
    return ordered


def _dedupe(tools: list[str]) -> list[str]:
    out: list[str] = []
    for t in tools:
        r = resolve_tool_name(t)
        if r not in out:
            out.append(r)
    return out
