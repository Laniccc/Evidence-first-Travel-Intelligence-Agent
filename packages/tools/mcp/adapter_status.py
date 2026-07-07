"""Which MCP policy tools have real adapters vs generic stubs."""

from __future__ import annotations

from tools.mcp.tool_specs import MCP_POLICY_SPECS

# Implemented adapters with dedicated upstream tool mappings.
IMPLEMENTED_MCP_POLICIES: frozenset[str] = frozenset({
    "search_mcp",
    "browser_mcp",
})

# policy_name -> [(server_key, upstream_tool_name), ...]
POLICY_TO_UPSTREAM: dict[str, list[tuple[str, str]]] = {
    "search_mcp": [
        ("search", "search"),
        ("search", "fetch-web"),
    ],
    "browser_mcp": [
        ("browser", "browser_navigate"),
        ("browser", "browser_snapshot"),
    ],
}


def is_mcp_policy_implemented(policy_name: str) -> bool:
    return policy_name in IMPLEMENTED_MCP_POLICIES


def implemented_mcp_policy_names() -> list[str]:
    return sorted(IMPLEMENTED_MCP_POLICIES)
