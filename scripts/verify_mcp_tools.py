#!/usr/bin/env python3
"""List upstream MCP tools per server (ground truth for adapter rollout)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "apps" / "agent-python"
sys.path.insert(0, str(AGENT))
sys.path.insert(0, str(ROOT / "packages"))

from app.config import Settings, get_settings  # noqa: E402
from tools.mcp.adapter_status import POLICY_TO_UPSTREAM  # noqa: E402
from tools.mcp.client_manager import get_mcp_client_manager, reset_mcp_client_manager  # noqa: E402


async def _verify_server(manager, server_name: str) -> dict:
    transport = manager.server_transport(server_name)
    row: dict = {"server": server_name, "transport": transport, "configured": manager.is_server_configured(server_name)}
    if not row["configured"]:
        row["error"] = manager.server_block_reason(server_name)
        return row

    if transport == "open_websearch_http":
        import httpx

        base = manager.server_url(server_name).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                health = await client.get(f"{base}/health")
                row["health_ok"] = health.status_code == 200
                row["tools"] = ["search", "fetch-web"]
        except Exception as exc:
            row["health_ok"] = False
            row["error"] = str(exc)
        return row

    result = await manager.list_server_tools(server_name)
    if result.ok:
        tools = result.data or []
        row["tools"] = [t.get("name") for t in tools if isinstance(t, dict) and t.get("name")]
    else:
        row["error"] = result.error
    return row


async def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    reset_mcp_client_manager()
    manager = get_mcp_client_manager(settings)

    servers = sorted({srv for pairs in POLICY_TO_UPSTREAM.values() for srv, _ in pairs})
    print("=== MCP verify (tools/list or HTTP health) ===\n")
    exit_code = 0
    for server in servers:
        row = await _verify_server(manager, server)
        status = "OK" if row.get("tools") or row.get("health_ok") else "FAIL"
        if status == "FAIL":
            exit_code = 1
        print(f"[{status}] {server} ({row.get('transport')})")
        if row.get("error"):
            print(f"  error: {row['error']}")
        if row.get("tools"):
            print(f"  tools: {', '.join(row['tools'])}")
        print()

    print("=== POLICY_TO_UPSTREAM ===")
    for policy, pairs in sorted(POLICY_TO_UPSTREAM.items()):
        upstream = " -> ".join(f"{s}/{t}" for s, t in pairs)
        print(f"  {policy}: {upstream}")

    await manager.close_stdio_sessions()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
