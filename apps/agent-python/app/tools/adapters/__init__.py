"""Compatibility exports for integrations-owned tool adapters."""

import importlib

MCPToolAdapter = importlib.import_module("app.integrations.mcp.mcp_tool_adapter").MCPToolAdapter

__all__ = ["MCPToolAdapter"]
