"""Register configured MCP policy tools on TravelToolRegistry."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.tools.adapters.mcp_tool_adapter import ConfiguredMCPTool
from app.tools.mcp.client_manager import get_mcp_client_manager
from app.tools.mcp.tool_specs import MCP_POLICY_SPECS, POLICY_TO_REGISTRY_ATTR

logger = logging.getLogger(__name__)


def attach_mcp_tools(registry) -> list[str]:
    """Attach MCP adapters for enabled+configured servers. Returns registered policy tool names."""
    settings = getattr(registry, "settings", None) or get_settings()
    if not settings.mcp_enabled:
        return []

    client = get_mcp_client_manager(settings)
    registered: list[str] = []

    for policy_name, (server_name, default_tool, capabilities) in MCP_POLICY_SPECS.items():
        if not client.is_server_configured(server_name):
            continue
        attr = POLICY_TO_REGISTRY_ATTR.get(policy_name, policy_name)
        if getattr(registry, attr, None) is not None:
            continue
        adapter = ConfiguredMCPTool(
            policy_name=policy_name,
            server_name=server_name,
            default_mcp_tool=default_tool,
            capabilities=capabilities,
            client=client,
        )
        setattr(registry, attr, adapter)
        registered.append(policy_name)
        logger.debug("Registered MCP tool %s -> %s (server=%s)", policy_name, attr, server_name)

    return registered
