from __future__ import annotations

import asyncio
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_autostart_attempted: set[str] = set()


def _npm_cache_env() -> str:
    cache = os.path.join(os.path.expanduser("~"), ".npm-cache")
    os.makedirs(cache, exist_ok=True)
    return cache


def _port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.get(url)
            return response.status_code == 200
    except Exception:
        return False


def _parse_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def _spawn_detached(command: str, *, new_window: bool) -> bool:
    try:
        if sys.platform == "win32" and new_window:
            CREATE_NEW_CONSOLE = 0x00000010
            subprocess.Popen(
                ["powershell", "-NoExit", "-Command", command],
                creationflags=CREATE_NEW_CONSOLE,
                close_fds=True,
            )
        elif sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-Command", command],
                close_fds=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["bash", "-lc", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return True
    except Exception as exc:
        logger.warning("MCP HTTP autostart spawn failed: %s", exc)
        return False


async def _wait_until_healthy(health_url: str, wait_seconds: float) -> bool:
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if await _http_ok(health_url, timeout=2.0):
            return True
        await asyncio.sleep(0.8)
    return await _http_ok(health_url, timeout=2.0)


def _find_listener_pids(host: str, port: int) -> list[int]:
    pids: set[int] = set()
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception as exc:
            logger.warning("netstat failed while finding listeners on %s:%s: %s", host, port, exc)
            return []
        hosts = {host, "0.0.0.0", "[::1]", "::1"}
        for line in result.stdout.splitlines():
            if "LISTENING" not in line.upper():
                continue
            match = re.search(r":(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$", line, re.I)
            if not match or int(match.group(1)) != port:
                continue
            if not any(h in line for h in hosts):
                continue
            pids.add(int(match.group(2)))
    else:
        for cmd in (
            ["ss", "-ltnp", f"sport = :{port}"],
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            except FileNotFoundError:
                continue
            for line in result.stdout.splitlines():
                for token in re.findall(r"pid=(\d+)", line):
                    pids.add(int(token))
                match = re.search(r"\s(\d+)/\S+\s*$", line)
                if match:
                    pids.add(int(match.group(1)))
            if pids:
                break
    return sorted(pids)


def _kill_process(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception as exc:
        logger.warning("Failed to kill PID %s: %s", pid, exc)
        return False


async def _cleanup_stale_listeners(host: str, port: int, *, wait_seconds: float = 3.0) -> list[int]:
    killed: list[int] = []
    for pid in _find_listener_pids(host, port):
        if _kill_process(pid):
            killed.append(pid)
    if not killed:
        return killed

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not _port_listening(host, port):
            break
        await asyncio.sleep(0.25)
    return killed


async def _ensure_search(settings: Any, *, new_window: bool, wait_seconds: float) -> str | None:
    if not settings.mcp_search_enabled:
        return None
    if (settings.mcp_search_transport or "").strip().lower() != "open_websearch_http":
        return None

    base = (settings.mcp_search_server_url or "").strip().rstrip("/")
    if not base:
        return None

    health_url = f"{base}/health"
    if await _http_ok(health_url):
        return "open-webSearch already healthy"

    host, port = _parse_host_port(base)
    notes: list[str] = []
    if _port_listening(host, port) and getattr(settings, "mcp_http_autostart_kill_stale", True):
        killed = await _cleanup_stale_listeners(host, port)
        if killed:
            notes.append(f"killed stale PIDs on :{port}: {', '.join(map(str, killed))}")
        if await _http_ok(health_url):
            prefix = "; ".join(notes)
            return f"{prefix}; open-webSearch healthy after cleanup" if prefix else "open-webSearch healthy after cleanup"
        if _port_listening(host, port):
            prefix = "; ".join(notes) if notes else "stale cleanup did not free port"
            return f"open-webSearch port still in use after cleanup ({prefix})"

    key = f"search:{base}"
    if key in _autostart_attempted:
        return "open-webSearch autostart already attempted this process"
    _autostart_attempted.add(key)

    cache = _npm_cache_env()
    engine = (getattr(settings, "mcp_search_default_engine", None) or "baidu").strip()
    use_proxy = bool(getattr(settings, "mcp_search_use_proxy", False))
    proxy_url = (getattr(settings, "mcp_search_proxy_url", None) or "http://127.0.0.1:7890").strip()
    proxy_env = (
        f"$env:USE_PROXY='true'; $env:PROXY_URL='{proxy_url}'; "
        if use_proxy
        else "$env:USE_PROXY='false'; "
    )
    cmd = (
        f"$env:npm_config_cache='{cache}'; "
        f"$env:DEFAULT_SEARCH_ENGINE='{engine}'; "
        f"$env:ENABLE_CORS='true'; "
        f"{proxy_env}"
        f"npx -y open-websearch@latest serve"
    )
    if not _spawn_detached(cmd, new_window=new_window):
        return "open-webSearch autostart spawn failed"

    if await _wait_until_healthy(health_url, wait_seconds):
        prefix = "; ".join(notes)
        return f"{prefix}; open-webSearch autostarted" if prefix else "open-webSearch autostarted"
    prefix = "; ".join(notes)
    suffix = "open-webSearch autostart launched but /health not ready yet"
    return f"{prefix}; {suffix}" if prefix else suffix


async def _ensure_openmeteo(settings: Any, *, new_window: bool, wait_seconds: float) -> str | None:
    if not settings.mcp_openmeteo_enabled:
        return None
    if (settings.mcp_openmeteo_transport or "").strip().lower() != "streamable_http":
        return None

    base = (settings.mcp_openmeteo_server_url or "").strip().rstrip("/")
    if not base:
        return None

    host, port = _parse_host_port(base)
    health_url = base if base.endswith("/mcp") else f"{base}/mcp"
    if await _http_ok(health_url):
        return "Open-Meteo MCP already healthy"

    notes: list[str] = []
    if _port_listening(host, port) and getattr(settings, "mcp_http_autostart_kill_stale", True):
        killed = await _cleanup_stale_listeners(host, port)
        if killed:
            notes.append(f"killed stale PIDs on :{port}: {', '.join(map(str, killed))}")
        if await _http_ok(health_url):
            prefix = "; ".join(notes)
            return f"{prefix}; Open-Meteo MCP healthy after cleanup" if prefix else "Open-Meteo MCP healthy after cleanup"
        if _port_listening(host, port):
            prefix = "; ".join(notes) if notes else "stale cleanup did not free port"
            return f"Open-Meteo MCP port still in use after cleanup ({prefix})"

    key = f"openmeteo:{base}"
    if key in _autostart_attempted:
        return "Open-Meteo autostart already attempted this process"
    _autostart_attempted.add(key)

    cache = _npm_cache_env()
    cmd = (
        f"$env:npm_config_cache='{cache}'; "
        f"$env:TRANSPORT='http'; $env:PORT='{port}'; "
        f"npx -y open-meteo-mcp-server"
    )
    if not _spawn_detached(cmd, new_window=new_window):
        return "Open-Meteo autostart spawn failed"

    await asyncio.sleep(min(wait_seconds, 3.0))
    if _port_listening(host, port, timeout=2.0) and await _http_ok(health_url, timeout=2.0):
        prefix = "; ".join(notes)
        return f"{prefix}; Open-Meteo MCP autostarted" if prefix else "Open-Meteo MCP autostarted"
    prefix = "; ".join(notes)
    suffix = "Open-Meteo autostart launched (not healthy yet)"
    return f"{prefix}; {suffix}" if prefix else suffix


async def ensure_http_mcp_services(settings: Any | None = None) -> list[str]:
    """Start HTTP MCP daemons if enabled, not healthy, and autostart is on."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    if not settings.mcp_enabled or not settings.mcp_http_autostart:
        return []

    new_window = settings.mcp_http_autostart_new_window
    wait_seconds = settings.mcp_http_autostart_wait_seconds

    notes: list[str] = []
    for coro in (
        _ensure_search(settings, new_window=new_window, wait_seconds=wait_seconds),
        _ensure_openmeteo(settings, new_window=new_window, wait_seconds=wait_seconds),
    ):
        msg = await coro
        if msg:
            notes.append(msg)
    return notes


def reset_http_autostart_state() -> None:
    _autostart_attempted.clear()
