"""Shared HTTP helpers for external/crawlers adapters."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import httpx

try:
    from dotenv import load_dotenv

    _ENV_FILE = Path(__file__).resolve().parents[2] / "apps" / "agent-python" / ".env"
    if _ENV_FILE.is_file():
        load_dotenv(_ENV_FILE)
except Exception:
    pass

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def proxy_url() -> str | None:
    return (os.environ.get("CRAWLER_PROXY_URL") or "").strip() or None


def fetch_timeout() -> float:
    try:
        return float(os.environ.get("CRAWLER_FETCH_TIMEOUT_SECONDS", "15"))
    except ValueError:
        return 15.0


def fetch_text(url: str) -> str:
    limit = fetch_timeout()
    timeout = httpx.Timeout(limit, connect=min(8.0, limit))
    headers = {"User-Agent": _DEFAULT_UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    proxy = proxy_url()
    client_kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": True, "headers": headers}
    if proxy:
        client_kwargs["proxy"] = proxy
    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def place_match_score(name: str, place: str) -> int:
    name_l = name.lower()
    place_l = place.lower()
    if not place_l:
        return 0
    if place_l in name_l or name_l in place_l:
        return 100
    tokens = [t for t in re.split(r"[\s,，、]+", place_l) if len(t) >= 2]
    return sum(30 for t in tokens if t in name_l)
