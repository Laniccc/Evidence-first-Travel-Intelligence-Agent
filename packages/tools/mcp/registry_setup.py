"""Register configured MCP policy tools on TravelToolRegistry."""

from __future__ import annotations

import logging

from app.config import get_settings
from tools.adapters.mcp_tool_adapter import ConfiguredMCPTool
from tools.mcp.adapters.baidu_map_adapter import BaiduMapMCPAdapter
from tools.mcp.adapters.browser_mcp_adapter import BrowserMCPAdapter
from tools.mcp.adapters.official_page_fetch_adapter import OfficialPageFetchAdapter
from tools.mcp.adapters.openmeteo_mcp_adapter import OpenMeteoMCPAdapter
from tools.mcp.adapters.osm_mcp_adapter import OsmMCPAdapter
from tools.mcp.adapters.search_mcp_adapter import SearchMCPAdapter
from tools.mcp.adapters.sqlite_mcp_adapter import SqliteMCPAdapter
from tools.mcp.adapters.wikipedia_mcp_adapter import WikipediaMCPAdapter
from tools.mcp.adapters.wikidata_mcp_adapter import WikidataMCPAdapter
from tools.mcp.adapter_status import IMPLEMENTED_MCP_POLICIES, is_mcp_policy_implemented
from tools.mcp.client_manager import get_mcp_client_manager
from tools.mcp.tool_specs import MCP_POLICY_SPECS, POLICY_TO_REGISTRY_ATTR

logger = logging.getLogger(__name__)


def _search_adapter(client, settings):
    transport = client.server_transport("search")
    if transport in {"open_websearch_http", "mock"}:
        return SearchMCPAdapter(client=client)
    if transport == "legacy_invoke":
        return ConfiguredMCPTool(
            policy_name="search_mcp",
            server_name="search",
            default_mcp_tool=settings.mcp_search_tool_name or "public_web_search",
            capabilities=MCP_POLICY_SPECS["search_mcp"][2],
            client=client,
        )
    return SearchMCPAdapter(client=client)


def _build_adapter(policy_name: str, server_name: str, client, settings):
    if policy_name == "search_mcp":
        return _search_adapter(client, settings)
    if policy_name == "official_page_reader_mcp":
        return OfficialPageFetchAdapter(client=client)
    if policy_name == "browser_mcp":
        return BrowserMCPAdapter(client=client)
    if policy_name in {"openmeteo_mcp", "weather_mcp", "climate_mcp"}:
        return OpenMeteoMCPAdapter(policy_name=policy_name, client=client)
    if policy_name in {"osm_mcp", "places_mcp", "geocode_mcp"}:
        return OsmMCPAdapter(policy_name=policy_name, client=client)
    if policy_name == "wikipedia_mcp":
        return WikipediaMCPAdapter(client=client)
    if policy_name == "wikidata_mcp":
        return WikidataMCPAdapter(client=client)
    if policy_name in {"sqlite_mcp", "evidence_store_mcp"}:
        return SqliteMCPAdapter(policy_name=policy_name, client=client)
    if policy_name in {
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "baidu_weather_mcp",
        "baidu_geocode_mcp",
        "baidu_reverse_geocode_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
        "baidu_ip_location_mcp",
    }:
        return BaiduMapMCPAdapter(policy_name=policy_name, client=client)

    _, default_tool, capabilities = MCP_POLICY_SPECS[policy_name]
    raise RuntimeError(
        f"Policy {policy_name!r} is in IMPLEMENTED_MCP_POLICIES but has no factory "
        f"(server={server_name!r}, default_tool={default_tool!r}, caps={capabilities!r})"
    )


def attach_mcp_tools(registry) -> list[str]:
    """Attach MCP adapters for enabled+configured servers. Returns registered policy tool names."""
    settings = getattr(registry, "settings", None) or get_settings()
    if not settings.mcp_enabled:
        return []

    client = get_mcp_client_manager(settings)
    registered: list[str] = []

    for policy_name, (server_name, _default_tool, _capabilities) in MCP_POLICY_SPECS.items():
        if not is_mcp_policy_implemented(policy_name):
            logger.debug("Skipping stub MCP registration for %s", policy_name)
            continue
        if policy_name not in IMPLEMENTED_MCP_POLICIES:
            logger.error("Refusing ConfiguredMCPTool fallback for unimplemented %s", policy_name)
            continue
        if not client.is_server_configured(server_name):
            continue
        attr = POLICY_TO_REGISTRY_ATTR.get(policy_name, policy_name)
        if getattr(registry, attr, None) is not None:
            continue

        adapter = _build_adapter(policy_name, server_name, client, settings)
        setattr(registry, attr, adapter)
        registered.append(policy_name)
        logger.debug("Registered MCP tool %s -> %s (server=%s)", policy_name, attr, server_name)

    return registered
