"""MCP integration facade."""

from app.integrations.mcp.delegated_runner import pick_tool_from_priority, run_delegated_mcp
from app.integrations.mcp.mcp_tool_adapter import MCPToolAdapter
from app.integrations.mcp.adapter_status import (
    implemented_mcp_policy_names,
    is_mcp_policy_implemented,
    is_mcp_policy_placeholder,
    is_ticket_provider_policy,
    mcp_policy_stub_reason,
)
from app.integrations.mcp.client_manager import MCPClientManager, MCPInvokeResult, get_mcp_client_manager

__all__ = [
    "MCPClientManager",
    "MCPInvokeResult",
    "MCPToolAdapter",
    "get_mcp_client_manager",
    "implemented_mcp_policy_names",
    "is_mcp_policy_implemented",
    "is_mcp_policy_placeholder",
    "is_ticket_provider_policy",
    "mcp_policy_stub_reason",
    "pick_tool_from_priority",
    "run_delegated_mcp",
]
