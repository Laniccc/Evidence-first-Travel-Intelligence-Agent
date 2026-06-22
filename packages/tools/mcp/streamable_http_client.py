from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from tools.mcp.stdio_client import StdioMCPSession

logger = logging.getLogger(__name__)


class StreamableHTTPMCPSession:
    """MCP client over Streamable HTTP (JSON-RPC POST to base URL)."""

    def __init__(
        self,
        server_name: str,
        base_url: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.server_name = server_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._next_id = 1
        self._initialized = False
        self._session_id: str | None = None

    async def list_tools(self) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        result = await self._request("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else result
        if isinstance(tools, list):
            return [t for t in tools if isinstance(t, dict)]
        return []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        await self._ensure_initialized()
        result = await self._request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        return StdioMCPSession._normalize_tool_result(result)

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "travel-agent", "version": "0.1.0"},
            },
        )
        await self._post_notification("notifications/initialized", {})
        self._initialized = True

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        response = await self._post_json(payload)
        if not isinstance(response, dict):
            raise RuntimeError(f"Invalid MCP response from {self.server_name}")
        if response.get("id") not in (None, request_id):
            raise RuntimeError(f"MCP response id mismatch for {self.server_name}")
        if "error" in response:
            err = response["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            detail = f" (code={code})" if code is not None else ""
            raise RuntimeError((message or f"MCP error from {self.server_name}") + detail)
        return response.get("result")

    async def _post_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        await self._post_json(payload)

    async def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()
            session_hdr = response.headers.get("mcp-session-id") or response.headers.get("Mcp-Session-Id")
            if session_hdr:
                self._session_id = session_hdr
            text = response.text.strip()
            if not text:
                return {}
            if text.startswith("event:") or text.startswith("data:"):
                return self._parse_sse_json(text)
            try:
                return response.json()
            except json.JSONDecodeError:
                for line in text.splitlines():
                    if line.startswith("data:"):
                        chunk = line[5:].strip()
                        if chunk:
                            return json.loads(chunk)
                raise RuntimeError(f"Unparseable MCP HTTP body from {self.server_name}")

    @staticmethod
    def _parse_sse_json(text: str) -> dict[str, Any]:
        for line in text.splitlines():
            if line.startswith("data:"):
                chunk = line[5:].strip()
                if chunk and chunk != "[DONE]":
                    return json.loads(chunk)
        return {}
