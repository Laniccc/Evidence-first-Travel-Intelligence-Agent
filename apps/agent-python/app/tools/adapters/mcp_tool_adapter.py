"""Compatibility exports for the integrations-owned MCP tool adapter."""

import importlib

MCPToolAdapter = importlib.import_module("app.integrations.mcp.mcp_tool_adapter").MCPToolAdapter

__all__ = ["MCPToolAdapter"]
