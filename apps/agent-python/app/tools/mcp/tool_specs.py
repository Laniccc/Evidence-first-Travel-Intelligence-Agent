"""Compatibility exports for integrations-owned MCP tool specs."""

import importlib

_impl = importlib.import_module("app.integrations.mcp.tool_specs")

MCP_POLICY_SPECS = _impl.MCP_POLICY_SPECS
MCP_POLICY_TOOL_NAMES = _impl.MCP_POLICY_TOOL_NAMES
NEED_TOOL_PROFILES = _impl.NEED_TOOL_PROFILES

__all__ = ["MCP_POLICY_SPECS", "MCP_POLICY_TOOL_NAMES", "NEED_TOOL_PROFILES"]
