import asyncio
import json
from pathlib import Path
import sys

import pytest
from mcp.client.stdio import StdioServerParameters

from app.integrations.mcp.stdio_session import BoundedStdioSession
from app.integrations.mcp.tool_catalog import MCPBoundaryError


def session(mode="normal", **kwargs):
    return BoundedStdioSession(StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parents[1] / "fakes" / "stdio_mcp_server.py"), mode]),
        **kwargs)


def assert_process_exited(client):
    pid = int(client.server_info["name"].rsplit("-", 1)[-1])
    if sys.platform == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            code = ctypes.c_ulong()
            kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            kernel.CloseHandle(ctypes.c_void_p(handle))
            assert code.value != 259
    else:
        import os
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


@pytest.mark.asyncio
async def test_real_subprocess_discovery_notifications_and_shutdown(caplog):
    client = session("notifications")
    async with client:
        assert set(client.catalog.names) == {"map_search_places", "map_place_details"}
        receipt = await client.call_tool("map_place_details", {"uid": "uid1"})
        value = json.loads(receipt.result["content"][0]["text"])
        assert value["calls"] == 1
        assert len(receipt.schema_hash) == 64 and receipt.call_id
        assert client.running
    assert not client.running
    assert "stderr-secret" not in caplog.text and "notification-secret" not in caplog.text
    assert_process_exited(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,args,code", [
    ("unlisted", {}, "tool_not_allowed"),
    ("map_place_details", {}, "invalid_arguments"),
    ("map_place_details", {"uid": 123}, "invalid_arguments"),
    ("map_place_details", {"uid": "x", "command": "bad"}, "invalid_arguments"),
])
async def test_invalid_tool_or_arguments_never_reach_server(name, args, code):
    async with session() as client:
        with pytest.raises(MCPBoundaryError, match=code):
            await client.call_tool(name, args)
        receipt = await client.call_tool("map_place_details", {"uid": "uid1"})
        assert json.loads(receipt.result["content"][0]["text"])["calls"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,code", [("pages", "discovery_budget_exhausted"),
                                      ("schema_large", "schema_size_exceeded")])
async def test_discovery_is_bounded_and_cleans_up(mode, code):
    client = session(mode)
    with pytest.raises(MCPBoundaryError, match=code):
        async with client:
            pytest.fail("must fail during discovery")
    assert not client.running
    assert_process_exited(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,code", [
    ("large", "result_size_exceeded"), ("tool_error", "tool_error"),
    ("timeout", "tool_timeout"), ("eof", "connection_closed"),
])
async def test_tool_failure_is_typed_and_session_closes(mode, code):
    client = session(mode, call_timeout_seconds=0.1)
    async with client:
        with pytest.raises(MCPBoundaryError, match=code):
            await client.call_tool("map_place_details", {"uid": "uid1"})
    assert not client.running
    assert_process_exited(client)


@pytest.mark.asyncio
async def test_schema_drift_rejects_new_definition():
    async with session("drift") as client:
        with pytest.raises(MCPBoundaryError, match="schema_drift"):
            await client.refresh_catalog()


@pytest.mark.asyncio
async def test_cancellation_closes_owner_and_subprocess():
    client = session("timeout")
    async with client:
        call = asyncio.create_task(client.call_tool("map_place_details", {"uid": "uid1"}))
        await client.call_started.wait()
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
    assert not client.running
    assert_process_exited(client)
