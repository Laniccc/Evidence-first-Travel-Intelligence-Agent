"""Map policy-level tool names to TravelToolRegistry attributes."""

from app.tools.mcp.tool_specs import MCP_POLICY_TOOL_NAMES, POLICY_TO_REGISTRY_ATTR

POLICY_TOOL_ALIASES: dict[str, str] = {
    "official_mcp": "official_page_reader_mcp",
    "mcp_weather": "weather_mcp",
    "mcp_places": "places_mcp",
    "mcp_official": "official_page_reader_mcp",
    "official_reader_mcp": "official_page_reader_mcp",
}


def resolve_tool_name(policy_name: str) -> str:
    if policy_name in POLICY_TO_REGISTRY_ATTR:
        return POLICY_TO_REGISTRY_ATTR[policy_name]
    return POLICY_TOOL_ALIASES.get(policy_name, policy_name)


def is_mcp_policy_tool(name: str) -> bool:
    return name in MCP_POLICY_TOOL_NAMES or name in {
        "official_mcp",
        "mcp_weather",
        "mcp_places",
        "mcp_official",
        "official_reader_mcp",
    }


def registry_tool_names() -> list[str]:
    from app.tools.registry import BASE_REGISTERED_TOOL_NAMES

    return sorted(set(BASE_REGISTERED_TOOL_NAMES))
