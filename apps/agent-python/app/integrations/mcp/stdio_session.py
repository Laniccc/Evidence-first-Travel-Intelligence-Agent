"""SDK session lifetime is owned by one task, never by individual HTTP requests."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import json
import logging
import os
import re
from uuid import uuid4

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.integrations.mcp.tool_catalog import MCPBoundaryError, ToolCatalog


@dataclass(frozen=True)
class ToolCallReceipt:
    tool: str
    call_id: str
    schema_hash: str
    result: dict


class _SafeSDKLog(logging.Filter):
    def filter(self, record):
        record.msg, record.args = "MCP transport diagnostic (payload redacted)", ()
        record.exc_info = None
        record.exc_text = None
        return True


def _boundary_error(error):
    if isinstance(error, MCPBoundaryError):
        return error
    if isinstance(error, BaseExceptionGroup):
        for child in error.exceptions:
            classified = _boundary_error(child)
            if classified.code != "connection_closed":
                return classified
    if isinstance(error, TimeoutError):
        return MCPBoundaryError("tool_timeout")
    return MCPBoundaryError("connection_closed")


class BoundedStdioSession:
    def __init__(self, parameters: StdioServerParameters, *, call_timeout_seconds=5.0,
                 startup_timeout_seconds=10.0, max_result_bytes=65536):
        if call_timeout_seconds <= 0 or startup_timeout_seconds <= 0 or max_result_bytes < 1:
            raise ValueError("invalid MCP limits")
        self.parameters = parameters.model_copy(deep=True)
        self.call_timeout = call_timeout_seconds
        self.startup_timeout = startup_timeout_seconds
        self.max_result_bytes = max_result_bytes
        self.catalog = None
        self.server_info = None
        self._baseline_hashes = None
        self._owner = None
        self.call_started = asyncio.Event()

    @property
    def running(self):
        return self._owner is not None and not self._owner.done()

    async def __aenter__(self):
        if self.running:
            raise MCPBoundaryError("session_already_open")
        self._queue = asyncio.Queue(maxsize=1)
        self._ready = asyncio.get_running_loop().create_future()
        self._owner = asyncio.create_task(self._serve(), name="travel-mcp-owner")
        try:
            await asyncio.shield(self._ready)
        except BaseException:
            await self.aclose()
            raise
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    async def aclose(self):
        if self._owner is None:
            return
        if not self._owner.done():
            self._owner.cancel()
        await asyncio.gather(self._owner, return_exceptions=True)

    async def restart(self):
        await self.aclose()
        return await self.__aenter__()

    async def call_tool(self, name, arguments):
        if self.catalog is None:
            raise MCPBoundaryError("session_not_ready")
        self.catalog.validate(name, arguments)
        return await self._submit("call", name, arguments)

    async def refresh_catalog(self):
        return await self._submit("refresh", None, None)

    async def _submit(self, operation, name, arguments):
        if not self.running:
            raise MCPBoundaryError("connection_closed")
        future = asyncio.get_running_loop().create_future()
        try:
            self._queue.put_nowait((operation, name, arguments, future))
        except asyncio.QueueFull:
            raise MCPBoundaryError("session_busy") from None
        try:
            return await future
        except asyncio.CancelledError:
            await self.aclose()
            raise

    async def _discover(self, session):
        cursor, tools, size = None, [], 0
        for _ in range(3):
            page = await session.list_tools(cursor=cursor)
            data = page.model_dump(mode="json", by_alias=True, exclude_none=True)
            size += len(json.dumps(data).encode())
            if size > 256 * 1024:
                raise MCPBoundaryError("schema_size_exceeded")
            tools.extend(data.get("tools", []))
            if len(tools) > 128:
                raise MCPBoundaryError("discovery_budget_exhausted")
            cursor = page.nextCursor
            if not cursor:
                return ToolCatalog(tools)
        raise MCPBoundaryError("discovery_budget_exhausted")

    async def _serve(self):
        active = None
        loggers = [logging.getLogger(name) for name in (
            "mcp.client.stdio", "mcp.client.session", "mcp.shared.session")]
        safe_log = _SafeSDKLog()
        for logger in loggers:
            logger.addFilter(safe_log)
        try:
            # Zero retained stderr bytes: OS sink drains without storing credentials.
            with open(os.devnull, "w", encoding="utf-8") as discarded_stderr:
                async with stdio_client(self.parameters, errlog=discarded_stderr) as streams:
                    async with ClientSession(*streams, read_timeout_seconds=timedelta(
                            seconds=max(self.call_timeout, self.startup_timeout) + 1)) as session:
                        async with asyncio.timeout(self.startup_timeout):
                            initialized = await session.initialize()
                            self.server_info = initialized.serverInfo.model_dump(mode="json")
                            discovered = await self._discover(session)
                            if self._baseline_hashes is not None and discovered.hashes != self._baseline_hashes:
                                raise MCPBoundaryError("schema_drift")
                            self.catalog = discovered
                            self._baseline_hashes = discovered.hashes
                        self._ready.set_result(True)
                        while True:
                            operation, name, arguments, active = await self._queue.get()
                            if active.cancelled():
                                continue
                            try:
                                async with asyncio.timeout(self.call_timeout):
                                    if operation == "refresh":
                                        refreshed = await self._discover(session)
                                        if refreshed.hashes != self.catalog.hashes:
                                            raise MCPBoundaryError("schema_drift")
                                        value = refreshed
                                    else:
                                        self.catalog.validate(name, arguments)
                                        self.call_started.set()
                                        result = await session.call_tool(name, arguments)
                                        data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
                                        if len(json.dumps(data).encode()) > self.max_result_bytes:
                                            raise MCPBoundaryError("result_size_exceeded")
                                        if result.isError:
                                            text = " ".join(str(block.get("text", "")) for block in data.get("content", []))
                                            code = "rate_limit" if re.search(r"\b429\b|rate.?limit|限流", text, re.I) else "tool_error"
                                            raise MCPBoundaryError(code)
                                        value = ToolCallReceipt(name, str(uuid4()),
                                            self.catalog.hashes[name], data)
                                if not active.done():
                                    active.set_result(value)
                            except Exception as exc:
                                classified = _boundary_error(exc)
                                if not active.done():
                                    active.set_exception(classified)
                                if classified.code in {"rate_limit", "tool_error"}:
                                    continue
                                # Any failed call invalidates the session; owner closes it.
                                return
                            finally:
                                active = None
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(_boundary_error(exc))
            if active is not None and not active.done():
                active.set_exception(_boundary_error(exc))
        finally:
            while not self._queue.empty():
                *_, future = self._queue.get_nowait()
                if not future.done():
                    future.set_exception(MCPBoundaryError("connection_closed"))
            for logger in loggers:
                logger.removeFilter(safe_log)
