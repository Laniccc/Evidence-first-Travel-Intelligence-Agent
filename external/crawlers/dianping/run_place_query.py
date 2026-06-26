#!/usr/bin/env python3
"""Dianping place-query adapter — keyword search + shop HTML parse."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from _adapter_common import fetch_text, place_match_score  # noqa: E402

_SHOP_LINK_RE = re.compile(
    r'<a[^>]+href="([^"]*dianping\.com/shop/\d+)[^"]*"[^>]*>([^<]{2,60})</a>',
    re.I,
)
_DATA_SHOP_RE = re.compile(
    r'data-shopname="([^"]+)"[^>]*data-address="([^"]*)"[^>]*(?:data-avgprice="([^"]*)")?',
    re.I,
)
_RATING_RE = re.compile(r"([\d.]+)\s*分")
_CROWD_RE = re.compile(r"排队|人多|拥挤|人少|清净|爆满")
_TICKET_RE = re.compile(r"门票|票价|预约|团购|套票|成人票|儿童票")


def _search_url(place: str, city: str | None, mode: str) -> str:
    if mode == "nearby":
        keyword = f"{city or ''} {place} 美食".strip()
    else:
        keyword = f"{city or ''} {place}".strip()
    return f"https://www.dianping.com/search/keyword/1/0_{quote(keyword)}"


def _nearby_items(html: str, source_url: str, max_results: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in _DATA_SHOP_RE.finditer(html):
        items.append(
            {
                "shop_name": match.group(1),
                "address": match.group(2) or None,
                "price_level": match.group(3) or None,
                "source_url": source_url,
                "confidence": 0.48,
            }
        )
        if len(items) >= max_results:
            return items
    for match in _SHOP_LINK_RE.finditer(html):
        items.append(
            {
                "shop_name": match.group(2).strip(),
                "source_url": match.group(1),
                "confidence": 0.45,
            }
        )
        if len(items) >= max_results:
            break
    return items


def _review_item(html: str, place: str, source_url: str) -> dict[str, Any]:
    item: dict[str, Any] = {
        "review_summary": f"大众点评 {place} 相关信号",
        "source_url": source_url,
        "confidence": 0.55,
    }
    crowd = _CROWD_RE.search(html)
    if crowd:
        item["crowd_risk"] = crowd.group(0)
    tickets = _TICKET_RE.findall(html)
    if tickets:
        item["ticket_related_mentions"] = tickets[:3]
    rating_match = _RATING_RE.search(html)
    if rating_match:
        item["rating"] = rating_match.group(1)
    title_match = re.search(r"<title>([^<]{2,120})</title>", html, re.I)
    if title_match:
        item["review_summary"] = title_match.group(1).strip()[:300]
    return item


def _pick_shop_url(html: str, place: str) -> str | None:
    best_url: str | None = None
    best_score = 0
    for match in _SHOP_LINK_RE.finditer(html):
        name = match.group(2).strip()
        score = place_match_score(name, place)
        if score > best_score:
            best_score = score
            best_url = match.group(1)
    return best_url


def run_query(place: str, city: str | None, mode: str, max_results: int) -> dict[str, Any]:
    search_url = _search_url(place, city, mode)
    try:
        html = fetch_text(search_url)
    except Exception as exc:
        return {"items": [], "error": str(exc)}

    if mode == "nearby":
        items = _nearby_items(html, search_url, max_results)
        return {"items": items}

    if mode == "ticket":
        shop_url = _pick_shop_url(html, place) or search_url
        try:
            shop_html = fetch_text(shop_url)
        except Exception:
            shop_html = html
        item = _review_item(shop_html, place, shop_url)
        tickets = _TICKET_RE.findall(shop_html)
        if tickets:
            item["ticket_related_mentions"] = tickets[:5]
        return {"items": [item]}

    shop_url = _pick_shop_url(html, place)
    if shop_url:
        try:
            shop_html = fetch_text(shop_url)
            return {"items": [_review_item(shop_html, place, shop_url)]}
        except Exception:
            pass
    return {"items": [_review_item(html, place, search_url)]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dianping vendor place query adapter")
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default="")
    parser.add_argument("--mode", default="review")
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args()
    result = run_query(args.place, args.city or None, args.mode, args.max_results)
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("items") else 1


if __name__ == "__main__":
    raise SystemExit(main())
