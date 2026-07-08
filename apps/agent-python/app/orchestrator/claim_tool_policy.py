"""Claim-level tool allowlists for S5 whitelist and gap-fill."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.tools.tool_name_resolver import resolve_tool_name
from tools.ticketing.provider_config import TICKET_PROVIDER_TOOL_NAMES

_TICKET_PLATFORM_FORBIDDEN_FOR_OPENING = frozenset(
    {
        "fliggy_ticket_api_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "ticket_price_history_query",
        "ticket_snapshot_store",
    }
)

_GEO_TOOLS = (
    "baidu_place_search_mcp",
    "baidu_place_detail_mcp",
    "baidu_geocode_mcp",
    "entity_resolution_agent",
    "osm_mcp",
)

_OFFICIAL_TOOLS = (
    "official_source_discovery_mcp",
    "official_page_reader_mcp",
    "browser_mcp",
    "search_mcp",
)

_SEARCH_TOOLS = ("search_mcp", "fact_search_agent", "keyword_search_agent")


@dataclass(frozen=True)
class ClaimToolPolicyView:
    claim_type: str
    allowed_domains: tuple[str, ...] = ()
    primary_tools: tuple[str, ...] = ()
    forbidden_tools: frozenset[str] = field(default_factory=frozenset)


CLAIM_TOOL_POLICY: dict[str, ClaimToolPolicyView] = {
    "opening_hours": ClaimToolPolicyView(
        claim_type="opening_hours",
        allowed_domains=("geo_resolution", "operation_status", "official_web", "search"),
        primary_tools=(
            *_GEO_TOOLS,
            *_OFFICIAL_TOOLS,
            "baidu_place_detail_mcp",
        ),
        forbidden_tools=_TICKET_PLATFORM_FORBIDDEN_FOR_OPENING,
    ),
    "ticket_price": ClaimToolPolicyView(
        claim_type="ticket_price",
        allowed_domains=("geo_resolution", "ticket_booking", "official_web", "search"),
        primary_tools=(
            *_GEO_TOOLS,
            *_OFFICIAL_TOOLS,
            "baidu_place_detail_mcp",
            "fliggy_ticket_api_mcp",
            "fliggy_ticket_snapshot_crawler_mcp",
            "ticketlens_experience_mcp",
            "ctrip_ticket_signal_crawler_mcp",
            "dianping_ticket_signal_crawler_mcp",
            "ticket_price_history_query",
        ),
        forbidden_tools=frozenset(),
    ),
}


def policy_for_claim(claim_type: str) -> ClaimToolPolicyView | None:
    return CLAIM_TOOL_POLICY.get(claim_type)


def primary_tools_for_claims(claim_types: list[str]) -> set[str]:
    out: set[str] = set()
    for ct in claim_types:
        pol = policy_for_claim(ct)
        if pol:
            out.update(pol.primary_tools)
    return out


def forbidden_tools_for_claims(claim_types: list[str]) -> set[str]:
    out: set[str] = set()
    for ct in claim_types:
        pol = policy_for_claim(ct)
        if pol:
            out.update(pol.forbidden_tools)
    if "opening_hours" in claim_types and "ticket_price" not in claim_types:
        out |= _TICKET_PLATFORM_FORBIDDEN_FOR_OPENING
    return out


def filter_allowed_tools(tools: list[str], claim_types: list[str]) -> list[str]:
    forbidden = forbidden_tools_for_claims(claim_types)
    out: list[str] = []
    for tool in tools:
        resolved = resolve_tool_name(tool)
        if resolved in forbidden:
            continue
        if resolved not in out:
            out.append(resolved)
    return out


def is_tool_allowed_for_claim(tool_name: str, claim_type: str) -> bool:
    resolved = resolve_tool_name(tool_name)
    pol = policy_for_claim(claim_type)
    if not pol:
        return True
    if resolved in pol.forbidden_tools:
        return False
    if claim_type == "ticket_price":
        if resolved in TICKET_PROVIDER_TOOL_NAMES or resolved in pol.primary_tools:
            return True
    return resolved in pol.primary_tools or resolved.endswith("_agent")
