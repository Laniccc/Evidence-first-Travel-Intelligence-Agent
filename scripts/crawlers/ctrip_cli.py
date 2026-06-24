#!/usr/bin/env python3
"""Ctrip crawler CLI — subprocess wrapper for CtripSpider or HTTP fallback."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _common import (  # noqa: E402
    _CROWD_RE,
    _PRICE_RE,
    _QUEUE_RE,
    _SEASON_RE,
    _TICKET_RE,
    emit_result,
    extract_snippets,
    fetch_url,
    heat_score_from_text,
    merge_stdin_payload,
    run_external_command,
)


def _search_url(place: str, city: str | None) -> str:
    query = f"{city or ''} {place} 景点".strip()
    return f"https://you.ctrip.com/sight/search?keyword={quote(query)}"


def _try_ctrip_spider(place: str, city: str | None, mode: str, max_results: int) -> dict[str, Any] | None:
    root = (os.environ.get("CTRIP_SPIDER_ROOT") or "").strip()
    if not root:
        return None
    entry = Path(root) / "run_place_query.py"
    if not entry.is_file():
        entry = Path(root) / "main.py"
    if not entry.is_file():
        return None
    argv = [
        sys.executable,
        str(entry),
        "--place",
        place,
        "--city",
        city or "",
        "--mode",
        mode,
        "--max-results",
        str(max_results),
    ]
    return run_external_command(argv, cwd=root)


def _item_from_html(
    html: str,
    *,
    place: str,
    mode: str,
    source_url: str,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source_url": source_url,
        "confidence": 0.5,
    }
    title_match = re.search(r"<title>([^<]{2,120})</title>", html, re.I)
    if title_match:
        item["review_summary"] = title_match.group(1).strip()[:300]
    heat = heat_score_from_text(html)
    if heat is not None:
        item["heat_score"] = heat
    crowd_snips = extract_snippets(html, _CROWD_RE)
    queue_snips = extract_snippets(html, _QUEUE_RE)
    if crowd_snips:
        item["crowd_risk"] = crowd_snips[0]
    if queue_snips:
        item["queue_risk"] = queue_snips[0]
    ticket_snips = extract_snippets(html, _TICKET_RE)
    if ticket_snips:
        item["ticket_related_mentions"] = ticket_snips[:3]
    price_snips = extract_snippets(html, _PRICE_RE)
    if price_snips:
        item["price_text"] = price_snips[0]
    season_snips = extract_snippets(html, _SEASON_RE)
    if season_snips:
        item["seasonality"] = season_snips[0]
        item["best_time_to_visit"] = season_snips[0]
    if mode == "guide" and season_snips:
        item["review_summary"] = season_snips[0]
    elif not item.get("review_summary"):
        item["review_summary"] = f"携程 {place} 页面信号"
    return item


def run_mode(place: str, city: str | None, mode: str, max_results: int, proxy_url: str | None) -> dict[str, Any]:
    external = _try_ctrip_spider(place, city, mode, max_results)
    if external and external.get("items"):
        return external

    url = _search_url(place, city)
    try:
        html = fetch_url(url, proxy_url=proxy_url)
    except Exception as exc:
        return {"items": [], "error": str(exc)}

    item = _item_from_html(html, place=place, mode=mode, source_url=url)
    if mode == "ticket":
        item["ticket_related_mentions"] = item.get("ticket_related_mentions") or extract_snippets(html, _TICKET_RE)
    if mode == "crowd":
        if not item.get("crowd_risk") and not item.get("queue_risk"):
            item["crowd_risk"] = "unknown"
    items = [item][: max(1, max_results)]
    return {"items": items}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ctrip place signal crawler CLI")
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default="")
    parser.add_argument("--country", default="China")
    parser.add_argument("--mode", default="review", choices=["review", "ticket", "guide", "crowd"])
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--proxy-url", default="")
    args = parser.parse_args()
    merged = merge_stdin_payload(
        {
            "place": args.place,
            "city": args.city or None,
            "country": args.country,
            "mode": args.mode,
            "max_results": args.max_results,
        }
    )
    place = str(merged.get("place") or "").strip()
    if not place:
        return emit_result({"items": [], "error": "missing place"}, exit_code=1)
    mode = str(merged.get("mode") or "review")
    if mode in {"ticket_price", "ticket_price_candidate"}:
        mode = "ticket"
    if mode in {"current_crowd_estimate", "queue_risk"}:
        mode = "crowd"
    if mode in {"best_time_to_visit", "seasonality"}:
        mode = "guide"
    result = run_mode(
        place,
        merged.get("city"),
        mode,
        int(merged.get("max_results") or 10),
        proxy_url=(args.proxy_url or None),
    )
    return emit_result(result, exit_code=0 if result.get("items") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
