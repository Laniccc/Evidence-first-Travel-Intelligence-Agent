from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from tools.mcp.stdio_client import StdioMCPSession, parse_command_args
from tools.mcp.streamable_http_client import StreamableHTTPMCPSession

logger = logging.getLogger(__name__)


class MCPInvokeResult(BaseModel):
    ok: bool = True
    data: Any = None
    error: str | None = None
    latency_ms: float = 0.0
    server_name: str = ""
    tool_name: str = ""


_SERVER_FIELDS: dict[str, dict[str, str]] = {
    "search": {
        "enabled": "mcp_search_enabled",
        "url": "mcp_search_server_url",
        "transport": "mcp_search_transport",
        "command": "mcp_search_command",
        "args": "mcp_search_args",
        "tool_name": "mcp_search_tool_name",
    },
    "browser": {
        "enabled": "mcp_browser_enabled",
        "url": "mcp_browser_server_url",
        "transport": "mcp_browser_transport",
        "command": "mcp_browser_command",
        "args": "mcp_browser_args",
    },
    "osm": {
        "enabled": "mcp_osm_enabled",
        "url": "mcp_osm_server_url",
        "transport": "mcp_osm_transport",
        "command": "mcp_osm_command",
        "args": "mcp_osm_args",
    },
    "openmeteo": {
        "enabled": "mcp_openmeteo_enabled",
        "url": "mcp_openmeteo_server_url",
        "transport": "mcp_openmeteo_transport",
        "command": "mcp_openmeteo_command",
        "args": "mcp_openmeteo_args",
        "tool_name": "mcp_openmeteo_tool_name",
    },
    "wikipedia": {
        "enabled": "mcp_wikipedia_enabled",
        "url": "mcp_wikipedia_server_url",
        "transport": "mcp_wikipedia_transport",
        "command": "mcp_wikipedia_command",
        "args": "mcp_wikipedia_args",
    },
    "wikidata": {
        "enabled": "mcp_wikidata_enabled",
        "url": "mcp_wikidata_server_url",
        "transport": "mcp_wikidata_transport",
        "command": "mcp_wikidata_command",
        "args": "mcp_wikidata_args",
    },
    "sqlite": {
        "enabled": "mcp_sqlite_enabled",
        "url": "mcp_sqlite_server_url",
        "transport": "mcp_sqlite_transport",
        "command": "mcp_sqlite_command",
        "args": "mcp_sqlite_args",
    },
}

_STDIO_TRANSPORTS = frozenset({"stdio", "stdio_or_http"})


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
    if _manager is not None:
        for session in _manager._stdio_sessions.values():
            proc = session._proc
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
        _manager._stdio_sessions.clear()
    _manager = None


class MCPClientManager:
    """MCP client with transport-aware configuration (HTTP search, streamable HTTP, stdio placeholder)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._mock_handlers: dict[tuple[str, str], Any] = {}
        self._stdio_sessions: dict[str, StdioMCPSession] = {}
        self._http_sessions: dict[str, StreamableHTTPMCPSession] = {}

    async def close_stdio_sessions(self) -> None:
        for session in list(self._stdio_sessions.values()):
            await session.close()
        self._stdio_sessions.clear()
        self._http_sessions.clear()

    async def list_server_tools(self, server_name: str) -> MCPInvokeResult:
        start = time.perf_counter()
        if not self.is_server_configured(server_name):
            return MCPInvokeResult(
                ok=False,
                error=self.server_block_reason(server_name),
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name="tools/list",
            )
        transport = self.server_transport(server_name)
        try:
            if transport == "streamable_http":
                session = self._http_session(server_name)
                tools = await session.list_tools()
            elif transport in _STDIO_TRANSPORTS or (
                transport == "stdio_or_http" and not self.server_url(server_name)
            ):
                session = self._stdio_session(server_name)
                tools = await session.list_tools()
            elif transport == "open_websearch_http":
                tools = [
                    {"name": "search", "description": "POST /search"},
                    {"name": "fetch-web", "description": "POST /fetch-web"},
                ]
            else:
                return MCPInvokeResult(
                    ok=False,
                    error=f"tools/list not supported for transport {transport}",
                    latency_ms=(time.perf_counter() - start) * 1000,
                    server_name=server_name,
                    tool_name="tools/list",
                )
            return MCPInvokeResult(
                ok=True,
                data=tools,
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name="tools/list",
            )
        except Exception as exc:
            return MCPInvokeResult(
                ok=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name="tools/list",
            )

    def register_mock_handler(self, server_name: str, tool_name: str, handler) -> None:
        self._mock_handlers[(server_name, tool_name)] = handler

    def is_globally_enabled(self) -> bool:
        return bool(self.settings.mcp_enabled)

    def _server_meta(self, server_name: str) -> dict[str, str] | None:
        return _SERVER_FIELDS.get(server_name)

    def is_server_enabled(self, server_name: str) -> bool:
        if not self.is_globally_enabled():
            return False
        meta = self._server_meta(server_name)
        if not meta:
            return False
        return bool(getattr(self.settings, meta["enabled"], False))

    def server_transport(self, server_name: str) -> str:
        meta = self._server_meta(server_name)
        if not meta:
            return ""
        raw = (getattr(self.settings, meta["transport"], None) or "").strip().lower()
        if raw:
            return raw
        url = self.server_url(server_name)
        if url == "mock://":
            return "mock"
        return "legacy_invoke"

    def server_url(self, server_name: str) -> str:
        meta = self._server_meta(server_name)
        if not meta:
            return ""
        return (getattr(self.settings, meta["url"], None) or "").strip()

    def server_command(self, server_name: str) -> str:
        meta = self._server_meta(server_name)
        if not meta or "command" not in meta:
            return ""
        return (getattr(self.settings, meta["command"], None) or "").strip()

    def server_args(self, server_name: str) -> str:
        meta = self._server_meta(server_name)
        if not meta or "args" not in meta:
            return ""
        return (getattr(self.settings, meta["args"], None) or "").strip()

    def server_block_reason(self, server_name: str) -> str:
        if not self.is_globally_enabled():
            return "MCP_ENABLED=false"
        meta = self._server_meta(server_name)
        if not meta:
            return f"Unknown MCP server {server_name!r}"
        enabled_field = meta["enabled"]
        if not getattr(self.settings, enabled_field, False):
            flag = enabled_field.upper()
            return f"{flag}=false"
        transport = self.server_transport(server_name)
        if transport in _STDIO_TRANSPORTS:
            if not self.server_command(server_name):
                return "stdio MCP: COMMAND missing"
            return "stdio MCP configured (command present)"
        if transport == "stdio_or_http":
            if self.server_url(server_name):
                return "server not configured"
            if not self.server_command(server_name):
                return "stdio_or_http: COMMAND or SERVER_URL required"
            return "stdio MCP configured (command present)"
        url = self.server_url(server_name)
        if not url:
            url_field = meta["url"].upper()
            return f"{url_field} missing"
        return "server not configured"

    def is_server_configured(self, server_name: str) -> bool:
        if not self.is_server_enabled(server_name):
            return False
        transport = self.server_transport(server_name)
        if transport in _STDIO_TRANSPORTS:
            return bool(self.server_command(server_name))
        if transport == "stdio_or_http":
            return bool(self.server_url(server_name)) or bool(self.server_command(server_name))
        url = self.server_url(server_name)
        if transport in {"open_websearch_http", "streamable_http", "legacy_invoke", "mock"}:
            return bool(url) or url == "mock://"
        if transport:
            return bool(url) or url == "mock://"
        return bool(url) or url == "mock://"

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
                error=self.server_block_reason(server_name),
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

        transport = self.server_transport(server_name)
        if transport == "open_websearch_http":
            return await self._invoke_open_websearch(server_name, tool_name, arguments, start)
        if transport == "streamable_http":
            return await self._invoke_streamable_http(server_name, tool_name, arguments, start)
        if transport in _STDIO_TRANSPORTS or (
            transport == "stdio_or_http" and not self.server_url(server_name)
        ):
            return await self._invoke_stdio(server_name, tool_name, arguments, start)

        return await self._invoke_legacy_http(server_name, tool_name, arguments, start, url)

    async def open_websearch_search(
        self,
        query: str,
        *,
        limit: int = 5,
        server_name: str = "search",
    ) -> MCPInvokeResult:
        return await self.invoke(
            server_name,
            self._default_tool_name(server_name, "search"),
            {"query": query, "limit": limit},
        )

    async def open_websearch_fetch(
        self,
        url: str,
        *,
        max_chars: int | None = None,
        server_name: str = "search",
    ) -> MCPInvokeResult:
        max_chars = max_chars or self.settings.mcp_max_result_chars
        return await self.invoke(
            server_name,
            "fetch",
            {"url": url, "maxChars": max_chars},
        )

    def _default_tool_name(self, server_name: str, fallback: str) -> str:
        meta = self._server_meta(server_name)
        if meta and "tool_name" in meta:
            configured = (getattr(self.settings, meta["tool_name"], None) or "").strip()
            if configured:
                return configured
        return fallback

    async def _invoke_open_websearch(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        start: float,
    ) -> MCPInvokeResult:
        base = self.server_url(server_name).rstrip("/")
        timeout = float(self.settings.mcp_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if tool_name in {"fetch", "fetch-web", "fetch_web"}:
                    payload = {
                        "url": arguments.get("url"),
                        "maxChars": arguments.get("maxChars") or self.settings.mcp_max_result_chars,
                    }
                    response = await client.post(f"{base}/fetch-web", json=payload)
                else:
                    payload = {
                        "query": arguments.get("query") or arguments.get("q") or "",
                        "limit": int(arguments.get("limit") or 5),
                    }
                    response = await client.post(f"{base}/search", json=payload)
                response.raise_for_status()
                data = response.json()
                data = self._truncate_payload(data)
                return MCPInvokeResult(
                    ok=True,
                    data=data,
                    latency_ms=(time.perf_counter() - start) * 1000,
                    server_name=server_name,
                    tool_name=tool_name,
                )
        except Exception as exc:
            logger.warning("open-webSearch call failed %s/%s: %s", server_name, tool_name, exc)
            return MCPInvokeResult(
                ok=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=tool_name,
            )

    async def _invoke_streamable_http(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        start: float,
    ) -> MCPInvokeResult:
        mcp_tool = tool_name or self._default_tool_name(server_name, "weather_forecast")
        try:
            session = self._http_session(server_name)
            data = await session.call_tool(mcp_tool, arguments)
            data = self._truncate_payload(data)
            return MCPInvokeResult(
                ok=True,
                data=data,
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=mcp_tool,
            )
        except Exception as exc:
            logger.warning("streamable HTTP MCP failed %s/%s: %s", server_name, mcp_tool, exc)
            return MCPInvokeResult(
                ok=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=mcp_tool,
            )

    def _http_session(self, server_name: str) -> StreamableHTTPMCPSession:
        existing = self._http_sessions.get(server_name)
        if existing is not None:
            return existing
        session = StreamableHTTPMCPSession(
            server_name,
            self.server_url(server_name),
            timeout=float(self.settings.mcp_timeout_seconds),
        )
        self._http_sessions[server_name] = session
        return session

    def _stdio_session(self, server_name: str) -> StdioMCPSession:
        existing = self._stdio_sessions.get(server_name)
        if existing is not None:
            return existing
        command = self.server_command(server_name)
        args = parse_command_args(self.server_args(server_name))
        timeout = float(self.settings.mcp_timeout_seconds)
        if server_name == "browser":
            timeout = float(getattr(self.settings, "mcp_browser_timeout_seconds", timeout))
        session = StdioMCPSession(
            server_name,
            command,
            args,
            timeout=timeout,
        )
        self._stdio_sessions[server_name] = session
        return session

    async def _invoke_stdio(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        start: float,
    ) -> MCPInvokeResult:
        try:
            session = self._stdio_session(server_name)
            data = await session.call_tool(tool_name, arguments)
            data = self._truncate_payload(data)
            return MCPInvokeResult(
                ok=True,
                data=data,
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=tool_name,
            )
        except Exception as exc:
            logger.warning("stdio MCP failed %s/%s: %s", server_name, tool_name, exc)
            return MCPInvokeResult(
                ok=False,
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
                server_name=server_name,
                tool_name=tool_name,
            )

    async def _invoke_legacy_http(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        start: float,
        url: str,
    ) -> MCPInvokeResult:
        payload = {"tool": tool_name, "arguments": arguments}
        timeout = float(self.settings.mcp_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url.rstrip("/") + "/invoke", json=payload)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "result" in data:
                    data = data["result"]
                data = self._truncate_payload(data)
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

    def _truncate_payload(self, data: Any) -> Any:
        text = json.dumps(data, ensure_ascii=False)
        if len(text) > self.settings.mcp_max_result_chars:
            return {"truncated": True, "preview": text[: self.settings.mcp_max_result_chars]}
        return data
