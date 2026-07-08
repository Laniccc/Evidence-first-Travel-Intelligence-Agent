"""Which MCP policy tools have real adapters vs generic stubs.

``is_server_configured`` only checks COMMAND/URL in .env — not whether calls work.
Use ``is_mcp_policy_implemented`` before whitelisting or registering adapters.
"""

from __future__ import annotations

from tools.mcp.tool_specs import MCP_POLICY_SPECS

# Dedicated adapters that map to real upstream tool names / HTTP endpoints.
IMPLEMENTED_MCP_POLICIES: frozenset[str] = frozenset(
    {
        "search_mcp",
        "official_page_reader_mcp",
        "browser_mcp",
        "openmeteo_mcp",
        "weather_mcp",
        "climate_mcp",
        "osm_mcp",
        "places_mcp",
        "geocode_mcp",
        "wikipedia_mcp",
        "wikidata_mcp",
        "sqlite_mcp",
        "evidence_store_mcp",
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "baidu_weather_mcp",
        "baidu_geocode_mcp",
        "baidu_reverse_geocode_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
        "baidu_ip_location_mcp",
    }
)

# policy_name -> [(server_key, upstream_tool_name), ...]
POLICY_TO_UPSTREAM: dict[str, list[tuple[str, str]]] = {
    "search_mcp": [
        ("search", "search"),
        ("search", "fetch-web"),
    ],
    "official_page_reader_mcp": [
        ("search", "fetch-web"),
    ],
    "browser_mcp": [
        ("browser", "browser_navigate"),
        ("browser", "browser_snapshot"),
    ],
    "openmeteo_mcp": [
        ("openmeteo", "geocoding"),
        ("openmeteo", "weather_forecast"),
    ],
    "weather_mcp": [
        ("openmeteo", "geocoding"),
        ("openmeteo", "weather_forecast"),
    ],
    "climate_mcp": [
        ("openmeteo", "geocoding"),
        ("openmeteo", "weather_archive"),
    ],
    "osm_mcp": [
        ("osm", "geocode_address"),
        ("osm", "find_nearby_places"),
        ("osm", "explore_area"),
    ],
    "places_mcp": [
        ("osm", "find_nearby_places"),
        ("osm", "search_category"),
    ],
    "geocode_mcp": [
        ("osm", "geocode_address"),
        ("osm", "reverse_geocode"),
    ],
    "wikipedia_mcp": [
        ("wikipedia", "wikipedia_search"),
        ("wikipedia", "wikipedia_get_summary"),
    ],
    "wikidata_mcp": [
        ("wikidata", "search_entity"),
        ("wikidata", "get_metadata"),
        ("wikidata", "get_properties"),
    ],
    "sqlite_mcp": [
        ("sqlite", "read_records"),
        ("sqlite", "query"),
        ("sqlite", "list_tables"),
    ],
    "evidence_store_mcp": [
        ("sqlite", "read_records"),
        ("sqlite", "query"),
        ("sqlite", "list_tables"),
    ],
    "baidu_place_search_mcp": [
        ("baidu_map", "map_search_places"),
        ("baidu_map", "map_geocode"),
    ],
    "baidu_place_detail_mcp": [
        ("baidu_map", "map_place_details"),
    ],
    "baidu_weather_mcp": [
        ("baidu_map", "map_weather"),
    ],
    "baidu_geocode_mcp": [
        ("baidu_map", "map_geocode"),
    ],
    "baidu_reverse_geocode_mcp": [
        ("baidu_map", "map_reverse_geocode"),
    ],
    "baidu_route_mcp": [
        ("baidu_map", "map_directions"),
    ],
    "baidu_route_matrix_mcp": [
        ("baidu_map", "map_directions_matrix"),
    ],
    "baidu_traffic_mcp": [
        ("baidu_map", "map_road_traffic"),
    ],
    "baidu_ip_location_mcp": [
        ("baidu_map", "map_ip_location"),
    ],
}

# S5 placeholder MCP policies — registered for domain planning but not implemented.
PLACEHOLDER_MCP_POLICIES: frozenset[str] = frozenset(
    {
        "fliggy_ticket_crawler_mcp",
        "meituan_ticket_crawler_mcp",
        "dianping_ticket_crawler_mcp",
        "qunar_ticket_crawler_mcp",
        "tourism_board_notice_mcp",
        "platform_notice_crawler_mcp",
        "mafengwo_note_crawler_mcp",
        "xiaohongshu_note_crawler_mcp",
        "review_signal_mcp",
        "public_review_search_mcp",
        "meituan_review_crawler_mcp",
        "qunar_review_crawler_mcp",
        "tripadvisor_review_crawler_mcp",
        "nearby_food_mcp",
        "nearby_rest_area_mcp",
        "nearby_toilet_mcp",
        "nearby_parking_mcp",
        "nearby_station_mcp",
        "nearby_attraction_mcp",
        "nearby_hotel_mcp",
        "meituan_nearby_crawler_mcp",
        "itinerary_planner_mcp",
        "route_feasibility_checker_mcp",
        "elderly_friendly_route_scorer_mcp",
        "family_trip_planner_mcp",
        "event_calendar_mcp",
    }
)


TICKET_PROVIDER_POLICIES: frozenset[str] = frozenset(
    {
        "ticketlens_experience_mcp",
        "ticketlens_experience_review_signal_mcp",
        "ctrip_review_crawler_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "ctrip_guide_crawler_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "fliggy_ticket_review_signal_mcp",
        "dianping_review_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "dianping_nearby_crawler_mcp",
        "ticket_snapshot_store",
        "ticket_price_history_query",
    }
)


def is_ticket_provider_policy(policy_name: str) -> bool:
    return policy_name in TICKET_PROVIDER_POLICIES


def is_mcp_policy_placeholder(policy_name: str) -> bool:
    if is_ticket_provider_policy(policy_name):
        return False
    return policy_name in PLACEHOLDER_MCP_POLICIES


def is_mcp_policy_implemented(policy_name: str) -> bool:
    return policy_name in IMPLEMENTED_MCP_POLICIES


def mcp_policy_stub_reason(policy_name: str) -> str | None:
    if policy_name not in MCP_POLICY_SPECS:
        return f"Unknown MCP policy tool {policy_name!r}"
    if is_mcp_policy_placeholder(policy_name):
        return f"not_implemented: placeholder MCP policy {policy_name!r} (provider not wired)"
    if is_mcp_policy_implemented(policy_name):
        return None
    server_name, default_tool, _ = MCP_POLICY_SPECS[policy_name]
    return (
        f"MCP stub: {policy_name} would call server {server_name!r} tool {default_tool!r} "
        f"(invented policy name — no adapter; only {sorted(IMPLEMENTED_MCP_POLICIES)} implemented)"
    )


def implemented_mcp_policy_names() -> list[str]:
    return sorted(IMPLEMENTED_MCP_POLICIES)
