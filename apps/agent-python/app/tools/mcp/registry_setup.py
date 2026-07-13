"""Compatibility exports for integrations-owned MCP registry setup."""

import importlib

attach_mcp_tools = importlib.import_module("app.integrations.mcp.registry_setup").attach_mcp_tools

__all__ = ["attach_mcp_tools"]
