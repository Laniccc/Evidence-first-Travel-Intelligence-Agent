"""Compatibility exports for integrations-owned MCP client manager."""

import importlib

_impl = importlib.import_module("app.integrations.mcp.client_manager")

MCPClientManager = _impl.MCPClientManager
MCPInvokeResult = _impl.MCPInvokeResult
get_mcp_client_manager = _impl.get_mcp_client_manager

__all__ = ["MCPClientManager", "MCPInvokeResult", "get_mcp_client_manager"]
