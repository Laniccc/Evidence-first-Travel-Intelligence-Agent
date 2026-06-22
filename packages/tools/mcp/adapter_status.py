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
}


def is_mcp_policy_implemented(policy_name: str) -> bool:
    return policy_name in IMPLEMENTED_MCP_POLICIES


def mcp_policy_stub_reason(policy_name: str) -> str | None:
    if policy_name not in MCP_POLICY_SPECS:
        return f"Unknown MCP policy tool {policy_name!r}"
    if is_mcp_policy_implemented(policy_name):
        return None
    server_name, default_tool, _ = MCP_POLICY_SPECS[policy_name]
    return (
        f"MCP stub: {policy_name} would call server {server_name!r} tool {default_tool!r} "
        f"(invented policy name — no adapter; only {sorted(IMPLEMENTED_MCP_POLICIES)} implemented)"
    )


def implemented_mcp_policy_names() -> list[str]:
    return sorted(IMPLEMENTED_MCP_POLICIES)
