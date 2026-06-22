from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_command_args(args_value: str) -> list[str]:
    """Parse comma-separated MCP_*_ARGS (e.g. `-y,@playwright/mcp@latest`)."""
    if not args_value or not args_value.strip():
        return []
    return [part.strip() for part in args_value.split(",") if part.strip()]


class StdioMCPSession:
    """Minimal MCP client over stdio (Content-Length framed JSON-RPC)."""

    def __init__(
        self,
        server_name: str,
        command: str,
        args: list[str],
        *,
        timeout: float = 10.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self.server_name = server_name
        self.command = command
        self.args = args
        self.timeout = timeout
        self.env = env
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._next_id = 1

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        async with self._lock:
            await self._ensure_initialized()
            result = await self._request(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
            return self._normalize_tool_result(result)

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self._lock:
            await self._ensure_initialized()
            result = await self._request("tools/list", {})
            tools = result.get("tools") if isinstance(result, dict) else result
            if isinstance(tools, list):
                return [t for t in tools if isinstance(t, dict)]
            return []

    async def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.returncode is None:
                self._proc.terminate()
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._proc.kill()
        except ProcessLookupError:
            pass
        self._proc = None
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized and self._proc is not None and self._proc.returncode is None:
            return
        await self._start_process()
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "travel-agent", "version": "0.1.0"},
            },
        )
        await self._send_notification("notifications/initialized", {})
        self._initialized = True

    async def _start_process(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        logger.info("Starting stdio MCP %s: %s %s", self.server_name, self.command, self.args)
        self._proc = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
        )

    async def _request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError(f"stdio MCP process not running for {self.server_name}")

        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        await self._write_message(payload)
        response = await asyncio.wait_for(self._read_message(), timeout=self.timeout)
        if not isinstance(response, dict):
            raise RuntimeError(f"Invalid MCP response from {self.server_name}")
        if response.get("id") != request_id:
            raise RuntimeError(f"MCP response id mismatch for {self.server_name}")
        if "error" in response:
            err = response["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            detail = f" (code={code})" if code is not None else ""
            raise RuntimeError((message or f"MCP error from {self.server_name}") + detail)
        return response.get("result")

    async def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError(f"stdio MCP process not running for {self.server_name}")
        await self._write_message({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def _write_message(self, message: dict[str, Any]) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        await self._proc.stdin.drain()

    async def _read_message(self) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdout is not None
        header_bytes = await self._read_until(self._proc.stdout, b"\r\n\r\n")
        header_text = header_bytes.decode("ascii", errors="replace")
        content_length = 0
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        if content_length <= 0:
            stderr_hint = await self._drain_stderr_hint()
            raise RuntimeError(
                f"Missing Content-Length in MCP header from {self.server_name}"
                + (f"; stderr: {stderr_hint}" if stderr_hint else "")
            )
        body = await self._proc.stdout.readexactly(content_length)
        return json.loads(body.decode("utf-8"))

    async def _drain_stderr_hint(self) -> str:
        if self._proc is None or self._proc.stderr is None:
            return ""
        try:
            data = await asyncio.wait_for(self._proc.stderr.read(2048), timeout=0.2)
            return data.decode("utf-8", errors="replace").strip()[:500]
        except Exception:
            return ""

    @staticmethod
    async def _read_until(stream: asyncio.StreamReader, delimiter: bytes) -> bytes:
        buffer = bytearray()
        while True:
            chunk = await stream.read(1)
            if not chunk:
                break
            buffer.extend(chunk)
            if buffer.endswith(delimiter):
                return bytes(buffer)

    @staticmethod
    def _normalize_tool_result(result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        if result.get("isError"):
            content = result.get("content") or []
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            raise RuntimeError("; ".join(texts) or "MCP tool returned isError=true")
        content = result.get("content") or []
        texts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if len(texts) == 1:
            text = texts[0]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"text": text, "claims": [{"claim_type": "travel_advice", "value": text}]}
        if texts:
            return {"text": "\n".join(texts), "claims": [{"claim_type": "travel_advice", "value": t} for t in texts]}
        return result
