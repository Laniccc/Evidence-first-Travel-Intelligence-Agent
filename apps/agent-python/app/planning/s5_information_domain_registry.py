"""Minimal legacy-domain bridge for the bounded RAG product.

The production state machine plans retrieval directly.  This registry remains only
for compatibility with generic planners and exposes no retired crawler capability.
"""

from __future__ import annotations

from .s5_information_domain import (
    InformationDomain,
    ProviderGroup,
    S5DomainToolBinding,
    S5ToolRole,
)

D = InformationDomain
P = ProviderGroup
R = S5ToolRole


def _binding(
    domain: InformationDomain,
    provider: ProviderGroup,
    tool: str,
    claims: list[str],
) -> S5DomainToolBinding:
    return S5DomainToolBinding(
        domain=domain,
        provider_group=provider,
        tool_name=tool,
        role=R.PRIMARY,
        capabilities=list(claims),
        claim_types=list(claims),
    )


S5_INFORMATION_DOMAIN_REGISTRY: dict[InformationDomain, list[S5DomainToolBinding]] = {
    D.GEO_RESOLUTION: [
        _binding(D.GEO_RESOLUTION, P.BAIDU_LBS_PROVIDER, "baidu_place_search_mcp", ["entity_resolution"]),
    ],
    D.GEO_FACT: [
        _binding(D.GEO_FACT, P.SEARCH_PROVIDER, "search_mcp", ["general_description"]),
    ],
    D.TICKET_BOOKING: [
        _binding(D.TICKET_BOOKING, P.OFFICIAL_WEB_PROVIDER, "official_page_reader_mcp", ["ticket_price"]),
    ],
    D.OPERATION_STATUS: [
        _binding(D.OPERATION_STATUS, P.OFFICIAL_WEB_PROVIDER, "official_page_reader_mcp", ["opening_hours", "visitor_notice"]),
    ],
    D.SEASONALITY: [
        _binding(D.SEASONALITY, P.SEARCH_PROVIDER, "search_mcp", ["seasonality"]),
    ],
    D.ROUTE_PLANNING: [
        _binding(D.ROUTE_PLANNING, P.BAIDU_LBS_PROVIDER, "baidu_route_mcp", ["distance", "duration"]),
    ],
    D.REALTIME_STATUS: [
        _binding(D.REALTIME_STATUS, P.WEATHER_PROVIDER, "weather_mcp", ["weather"]),
    ],
}


def bindings_for_domain(domain: InformationDomain) -> list[S5DomainToolBinding]:
    return list(S5_INFORMATION_DOMAIN_REGISTRY.get(domain, []))


def all_registered_tool_names() -> set[str]:
    return {
        binding.tool_name
        for bindings in S5_INFORMATION_DOMAIN_REGISTRY.values()
        for binding in bindings
    }


def placeholder_tool_names() -> set[str]:
    return set()


def provider_groups_for_domains(domains: list[InformationDomain]) -> list[ProviderGroup]:
    return list(dict.fromkeys(binding.provider_group for domain in domains for binding in bindings_for_domain(domain)))
