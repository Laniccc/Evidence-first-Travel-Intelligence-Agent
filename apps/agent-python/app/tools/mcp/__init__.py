"""Compatibility exports for integrations-owned MCP modules."""

import importlib

_impl = importlib.import_module("app.integrations.mcp")

MCPClientManager = _impl.MCPClientManager
MCPInvokeResult = _impl.MCPInvokeResult
MCPToolAdapter = _impl.MCPToolAdapter
get_mcp_client_manager = _impl.get_mcp_client_manager
implemented_mcp_policy_names = _impl.implemented_mcp_policy_names
is_mcp_policy_implemented = _impl.is_mcp_policy_implemented
is_mcp_policy_placeholder = _impl.is_mcp_policy_placeholder
is_ticket_provider_policy = _impl.is_ticket_provider_policy
mcp_policy_stub_reason = _impl.mcp_policy_stub_reason
pick_tool_from_priority = _impl.pick_tool_from_priority
run_delegated_mcp = _impl.run_delegated_mcp

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
