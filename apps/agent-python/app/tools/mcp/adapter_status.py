"""Compatibility exports for integrations-owned MCP adapter status."""

import importlib

_impl = importlib.import_module("app.integrations.mcp.adapter_status")

implemented_mcp_policy_names = _impl.implemented_mcp_policy_names
is_mcp_policy_implemented = _impl.is_mcp_policy_implemented
is_mcp_policy_placeholder = _impl.is_mcp_policy_placeholder
is_ticket_provider_policy = _impl.is_ticket_provider_policy
mcp_policy_stub_reason = _impl.mcp_policy_stub_reason

__all__ = [
    "implemented_mcp_policy_names",
    "is_mcp_policy_implemented",
    "is_mcp_policy_placeholder",
    "is_ticket_provider_policy",
    "mcp_policy_stub_reason",
]
