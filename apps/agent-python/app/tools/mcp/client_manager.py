from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class MCPInvokeResult(BaseModel):
    ok: bool = True
    data: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    server_name: str = ""
    tool_name: str = ""


_SERVER_FIELDS: dict[str, tuple[str, str]] = {
    "search": ("mcp_search_enabled", "mcp_search_server_url"),
    "browser": ("mcp_browser_enabled", "mcp_browser_server_url"),
    "osm": ("mcp_osm_enabled", "mcp_osm_server_url"),
    "openmeteo": ("mcp_openmeteo_enabled", "mcp_openmeteo_server_url"),
    "wikipedia": ("mcp_wikipedia_enabled", "mcp_wikipedia_server_url"),
    "wikidata": ("mcp_wikidata_enabled", "mcp_wikidata_server_url"),
    "sqlite": ("mcp_sqlite_enabled", "mcp_sqlite_server_url"),
}


_manager: "MCPClientManager | None" = None


def get_mcp_client_manager(settings: Settings | None = None) -> "MCPClientManager":
    global _manager
    if _manager is None:
        _manager = MCPClientManager(settings)
    elif settings is not None:
        _manager.settings = settings
    return _manager


def reset_mcp_client_manager() -> None:
    global _manager
    _manager = None


class MCPClientManager:
    """Generic MCP client — server URLs and flags from Settings; not tied to a specific GitHub MCP."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._mock_handlers: dict[tuple[str, str], Any] = {}

    def register_mock_handler(self, server_name: str, tool_name: str, handler) -> None:
        self._mock_handlers[(server_name, tool_name)] = handler

    def is_globally_enabled(self) -> bool:
        return bool(self.settings.mcp_enabled)

    def is_server_enabled(self, server_name: str) -> bool:
        if not self.is_globally_enabled():
            return False
        enabled_field, _ = _SERVER_FIELDS.get(server_name, ("", ""))
        if not enabled_field:
            return False
        return bool(getattr(self.settings, enabled_field, False))

    def is_server_configured(self, server_name: str) -> bool:
        if not self.is_server_enabled(server_name):
            return False
        _, url_field = _SERVER_FIELDS.get(server_name, ("", ""))
        if not url_field:
            return False
        url = (getattr(self.settings, url_field, None) or "").strip()
        return bool(url) or url == "mock://"

    def server_url(self, server_name: str) -> str:
        _, url_field = _SERVER_FIELDS.get(server_name, ("", ""))
        return (getattr(self.settings, url_field, None) or "").strip()

    async def invoke(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPInvokeResult:
        arguments = arguments or {}
        start = time.perf_counter()

        if not self.is_server_configured(server_name):
            return MCPInvokeResult(
                ok=False,
                error=f"MCP server {server_name!r} not enabled or URL missing",
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=tool_name,
            )

        handler = self._mock_handlers.get((server_name, tool_name))
        if handler is not None:
            try:
                data = handler(arguments)
                if hasattr(data, "__await__"):
                    data = await data
                return MCPInvokeResult(
                    ok=True,
                    data=data,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    server_name=server_name,
                    tool_name=tool_name,
                )
            except Exception as exc:
                return MCPInvokeResult(
                    ok=False,
                    error=str(exc),
                    latency_ms=(time.perf_counter() - start) * 1000,
                    server_name=server_name,
                    tool_name=tool_name,
                )

        url = self.server_url(server_name)
        if url == "mock://":
            return MCPInvokeResult(
                ok=False,
                error=f"No mock handler for {server_name}/{tool_name}",
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=tool_name,
            )

        payload = {"tool": tool_name, "arguments": arguments}
        timeout = float(self.settings.mcp_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url.rstrip("/") + "/invoke", json=payload)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "result" in data:
                    data = data["result"]
                text = json.dumps(data, ensure_ascii=False)
                if len(text) > self.settings.mcp_max_result_chars:
                    data = {"truncated": True, "preview": text[: self.settings.mcp_max_result_chars]}
                return MCPInvokeResult(
                    ok=True,
                    data=data,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    server_name=server_name,
                    tool_name=tool_name,
                )
        except Exception as exc:
            logger.warning("MCP invoke failed %s/%s: %s", server_name, tool_name, exc)
            return MCPInvokeResult(
                ok=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=tool_name,
            )
