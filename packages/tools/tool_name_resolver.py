"""Map policy-level tool names to TravelToolRegistry attributes."""

from tools.mcp.tool_specs import MCP_POLICY_TOOL_NAMES, POLICY_TO_REGISTRY_ATTR
from tools.official_source.registry_setup import is_official_source_tool
from tools.ticketing.provider_config import (
    is_crowd_provider_tool,
    is_ticket_provider_tool,
)

POLICY_TOOL_ALIASES: dict[str, str] = {
    "official_mcp": "official_page_reader_mcp",
    "mcp_weather": "weather_mcp",
    "mcp_places": "places_mcp",
    "mcp_official": "official_page_reader_mcp",
    "official_reader_mcp": "official_page_reader_mcp",
    "official_source_classifier": "official_source_discovery_mcp",
    # Deprecated S5 placeholder names → implemented ticket/review providers
    "ctrip_ticket_crawler_mcp": "ctrip_ticket_signal_crawler_mcp",
    "ctrip_review_signal_mcp": "ctrip_review_crawler_mcp",
    "dianping_review_signal_mcp": "dianping_review_crawler_mcp",
    "fliggy_ticket_snapshot_crawler_mcp": "fliggy_ticket_api_mcp",
    "fliggy_ticket_signal_mcp": "fliggy_ticket_api_mcp",
    "feizhu_ticket_api_mcp": "fliggy_ticket_api_mcp",
}


def resolve_tool_name(policy_name: str) -> str:
    if policy_name in POLICY_TO_REGISTRY_ATTR:
        return POLICY_TO_REGISTRY_ATTR[policy_name]
    return POLICY_TOOL_ALIASES.get(policy_name, policy_name)


def is_mcp_policy_tool(name: str) -> bool:
    if is_ticket_provider_tool(name) or is_crowd_provider_tool(name) or is_official_source_tool(name):
        return False
    return name in MCP_POLICY_TOOL_NAMES or name in {
        "official_mcp",
        "mcp_weather",
        "mcp_places",
        "mcp_official",
        "official_reader_mcp",
    }


def registry_tool_names() -> list[str]:
    from tools.registry import BASE_REGISTERED_TOOL_NAMES

    return sorted(set(BASE_REGISTERED_TOOL_NAMES))
