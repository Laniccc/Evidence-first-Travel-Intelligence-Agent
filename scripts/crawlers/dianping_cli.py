#!/usr/bin/env python3
"""Dianping crawler CLI — review (dianping-crawler) and nearby (dianping_spider) modes."""

from __future__ import annotations

import argparse
import json
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
    _QUEUE_RE,
    _TICKET_RE,
    emit_result,
    extract_snippets,
    fetch_url,
    merge_stdin_payload,
    run_external_command,
)


def _try_dianping_crawler(place: str, city: str | None, mode: str, max_results: int) -> dict[str, Any] | None:
    root = (os.environ.get("DIANPING_CRAWLER_ROOT") or "").strip()
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


def _try_dianping_spider(place: str, city: str | None, max_results: int) -> dict[str, Any] | None:
    cmd = (os.environ.get("DIANPING_SPIDER_COMMAND") or "").strip()
    if not cmd:
        return None
    argv = cmd.format(
        place=place,
        city=city or "",
        query=place,
        mode="nearby",
        max_results=max_results,
    ).split()
    workdir = (os.environ.get("DIANPING_SPIDER_WORKDIR") or "").strip() or None
    return run_external_command(argv, cwd=workdir)


def _normalize_shop(shop: dict[str, Any]) -> dict[str, Any]:
    name = shop.get("shop_name") or shop.get("name") or shop.get("title")
    return {
        "shop_name": name,
        "address": shop.get("address"),
        "lat": shop.get("lat"),
        "lng": shop.get("lng"),
        "rating": shop.get("rating") or shop.get("comment_score"),
        "main_category": shop.get("main_category_name") or shop.get("category"),
        "source_url": shop.get("source_url") or shop.get("url"),
        "confidence": float(shop.get("confidence", 0.5)),
    }


def _review_from_html(html: str, place: str, source_url: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "review_summary": f"大众点评 {place} 相关信号",
        "source_url": source_url,
        "confidence": 0.5,
    }
    crowd = extract_snippets(html, _CROWD_RE)
    queue = extract_snippets(html, _QUEUE_RE)
    tickets = extract_snippets(html, _TICKET_RE)
    if crowd:
        item["crowd_risk"] = crowd[0]
    if queue:
        item["queue_risk"] = queue[0]
    if tickets:
        item["ticket_related_mentions"] = tickets[:3]
    rating_match = re.search(r"([\d.]+)\s*分", html)
    if rating_match:
        item["rating"] = rating_match.group(1)
    return item


def _nearby_from_html(html: str, place: str, source_url: str, max_results: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in re.finditer(
        r'data-shopname="([^"]+)"[^>]*data-address="([^"]*)"[^>]*data-avgprice="([^"]*)"',
        html,
    ):
        items.append(
            {
                "shop_name": match.group(1),
                "address": match.group(2),
                "price_level": match.group(3),
                "source_url": source_url,
                "confidence": 0.45,
            }
        )
        if len(items) >= max_results:
            break
    if items:
        return items
    for match in re.finditer(r"<a[^>]+href=\"([^\"]*dianping\.com/shop/\d+)[^\"]*\"[^>]*>([^<]{2,40})</a>", html):
        items.append(
            {
                "shop_name": match.group(2).strip(),
                "source_url": match.group(1),
                "confidence": 0.4,
            }
        )
        if len(items) >= max_results:
            break
    if not items:
        items.append(
            {
                "shop_name": f"{place} 周边商户",
                "review_summary": f"大众点评搜索 {place}",
                "source_url": source_url,
                "confidence": 0.35,
            }
        )
    return items


def _shop_payload_to_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data.get("shop_name"):
        return [_normalize_shop(data)]
    items = data.get("items") or data.get("nearby_poi") or []
    if isinstance(items, dict):
        items = [items]
    out: list[dict[str, Any]] = []
    for raw in items:
        if isinstance(raw, dict):
            out.append(_normalize_shop(raw))
    return out


def run_review(place: str, city: str | None, max_results: int) -> dict[str, Any]:
    external = _try_dianping_crawler(place, city, "review", max_results)
    if external:
        items = _shop_payload_to_items(external)
        if not items and external.get("default_reviews"):
            reviews = external["default_reviews"].get("review_info") or []
            texts = [r.get("content") for r in reviews if isinstance(r, dict) and r.get("content")]
            if texts:
                items = [
                    {
                        "review_summary": texts[0][:500],
                        "source_url": external.get("source_url"),
                        "confidence": 0.55,
                    }
                ]
        if items:
            return {"items": items[:max_results]}

    url = f"https://www.dianping.com/search/keyword/1/0_{quote(place)}"
    try:
        html = fetch_url(url)
    except Exception as exc:
        return {"items": [], "error": str(exc)}
    return {"items": [_review_from_html(html, place, url)]}


def run_nearby(place: str, city: str | None, max_results: int) -> dict[str, Any]:
    external = _try_dianping_spider(place, city, max_results)
    if external:
        items = external.get("items") or external.get("nearby_poi") or []
        if isinstance(items, list) and items:
            return {"items": [_normalize_shop(i) for i in items[:max_results] if isinstance(i, dict)]}

    external = _try_dianping_crawler(place, city, "nearby", max_results)
    if external and external.get("items"):
        return {"items": _shop_payload_to_items(external)[:max_results]}

    url = f"https://www.dianping.com/search/keyword/1/0_{quote(f'{city or ''} {place} 美食'.strip())}"
    try:
        html = fetch_url(url)
    except Exception as exc:
        return {"items": [], "error": str(exc)}
    return {"items": _nearby_from_html(html, place, url, max_results)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dianping crawler CLI")
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default="")
    parser.add_argument("--country", default="China")
    parser.add_argument("--mode", default="review", choices=["review", "nearby", "ticket"])
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()
    merged = merge_stdin_payload(
        {
            "place": args.place,
            "city": args.city or None,
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
    max_results = int(merged.get("max_results") or 10)
    city = merged.get("city")

    if mode == "nearby":
        result = run_nearby(place, city, max_results)
    else:
        result = run_review(place, city, max_results)

    return emit_result(result, exit_code=0 if result.get("items") else 1)


if __name__ == "__main__":
    raise SystemExit(main())
