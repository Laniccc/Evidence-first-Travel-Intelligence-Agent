"""Shared helpers for local crawler CLI wrappers."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any

import httpx

_CROWD_RE = re.compile(r"排队|人多|拥挤|人少|清净|爆满")
_QUEUE_RE = re.compile(r"排队|等了很久|排队久|人山人海")
_TICKET_RE = re.compile(
    r"门票|票价|预约|团购|套票|成人票|儿童票|购票|收费|免票|半价|索道|缆车|进山费"
)
_PRICE_RE = re.compile(r"[¥￥]\s*\d+(?:\.\d+)?(?:\s*起)?|\d+(?:\.\d+)?\s*元")
_SEASON_RE = re.compile(
    r"最佳旅游时间|适宜游玩|游玩季节|推荐季节|最佳季节|几月|春季|夏季|秋季|冬季|淡季|旺季"
)
_HEAT_RE = re.compile(r"热度\s*[:：]?\s*([\d.]+)|heat[_\s]?score[\"']?\s*[:=]\s*([\d.]+)", re.I)


def merge_stdin_payload(args: dict[str, Any]) -> dict[str, Any]:
    """Merge BaseCrawlerTool stdin JSON over CLI args."""
    if sys.stdin is None or sys.stdin.isatty():
        return args
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return args
    if not isinstance(payload, dict):
        return args
    out = dict(args)
    for key in ("place_name", "city", "country", "query", "claim_type", "max_results"):
        if payload.get(key) not in (None, ""):
            out[key] = payload[key]
    if payload.get("place_name") and not out.get("place"):
        out["place"] = payload["place_name"]
    if payload.get("query") and not out.get("place"):
        out["place"] = payload["query"]
    mode = payload.get("mode") or payload.get("claim_type")
    if mode and not out.get("mode"):
        out["mode"] = str(mode)
    return out


def emit_result(payload: dict[str, Any], *, exit_code: int = 0) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    return exit_code


def run_external_command(argv: list[str], *, timeout: float = 30.0, cwd: str | None = None) -> dict[str, Any] | None:
    if not argv:
        return None
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd or None,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {"items": data}
    except json.JSONDecodeError:
        return {"items": [{"review_summary": text[:500], "confidence": 0.4}]}


def fetch_url(url: str, *, timeout: float = 15.0, proxy_url: str | None = None) -> str:
    proxies = proxy_url or os.environ.get("CRAWLER_PROXY_URL") or None
    client_kwargs: dict[str, Any] = {"timeout": timeout, "follow_redirects": True}
    if proxies:
        client_kwargs["proxy"] = proxies
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    with httpx.Client(**client_kwargs) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


def extract_snippets(text: str, pattern: re.Pattern[str], *, limit: int = 3) -> list[str]:
    hits: list[str] = []
    for match in pattern.finditer(text):
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 80)
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        if snippet and snippet not in hits:
            hits.append(snippet[:200])
        if len(hits) >= limit:
            break
    return hits


def heat_score_from_text(text: str) -> float | None:
    match = _HEAT_RE.search(text)
    if not match:
        return None
    raw = next((g for g in match.groups() if g), None)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
