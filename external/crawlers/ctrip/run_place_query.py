#!/usr/bin/env python3
"""Ctrip place-query adapter — search sight + pull comment snippets via CtripSpider API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from _adapter_common import fetch_text, place_match_score, proxy_url  # noqa: E402

_VENDOR = _ROOT / "vendors" / "CtripSpider"
_SIGHT_LINK_RE = re.compile(r'href="(https?://you\.ctrip\.com/sight/[^"#?]+)"', re.I)
_TITLE_RE = re.compile(r"<title>([^<]{2,160})</title>", re.I)
_TICKET_RE = re.compile(r"门票|票价|预约|团购|套票|成人票|儿童票|购票|收费|免票")
_CROWD_RE = re.compile(r"排队|人多|拥挤|人少|清净")
_SEASON_RE = re.compile(r"最佳旅游时间|适宜游玩|游玩季节|推荐季节|几月|淡季|旺季")


def _search_sight_url(place: str, city: str | None) -> tuple[str | None, str | None]:
    query = f"{city or ''} {place} 景点".strip()
    url = f"https://you.ctrip.com/sight/search?keyword={quote(query)}"
    html = fetch_text(url)
    best_url: str | None = None
    best_title: str | None = None
    best_score = 0
    for match in _SIGHT_LINK_RE.finditer(html):
        href = match.group(1)
        title_match = re.search(r"/([^/]+)\.html", href)
        title = title_match.group(1) if title_match else href
        title = title.replace("-", " ")
        score = place_match_score(title, place)
        if score > best_score:
            best_score = score
            best_url = href
            best_title = title
    if not best_url:
        title_match = _TITLE_RE.search(html)
        if title_match and place in title_match.group(1):
            return url, title_match.group(1).strip()
    return best_url, best_title


def _resource_id_from_url(sight_url: str) -> str | None:
    match = re.search(r"/(\d+)\.html", sight_url)
    return match.group(1) if match else None


def _patch_vendor_proxy() -> None:
    proxy = proxy_url()
    if not proxy or not _VENDOR.is_dir():
        return
    if str(_VENDOR) not in sys.path:
        sys.path.insert(0, str(_VENDOR))

    def _env_proxy() -> dict[str, str]:
        return {"http": proxy, "https": proxy}

    import utils.proxy  # type: ignore[import-untyped]

    utils.proxy.my_get_proxy = _env_proxy  # type: ignore[attr-defined]


def _comments_via_vendor(resource_id: str, *, max_items: int) -> list[dict[str, Any]]:
    if not _VENDOR.is_dir():
        return []
    _patch_vendor_proxy()
    try:
        from rich.console import Console  # type: ignore[import-untyped]
        from xiecheng.xiecheng_api import XieCheng  # type: ignore[import-untyped]
    except ImportError:
        return []

    xc = XieCheng(Console(width=120, stderr=False))
    items: list[dict[str, Any]] = []
    for page in range(1, 4):
        raw = xc.get_scene_comments(int(resource_id), page, 10)
        if not raw or not isinstance(raw, dict):
            break
        for row in (raw.get("result") or {}).get("items") or []:
            if not isinstance(row, dict):
                continue
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            items.append(
                {
                    "review_summary": content[:500],
                    "source_url": row.get("jumpUrl") or row.get("url"),
                    "confidence": 0.58,
                }
            )
            if len(items) >= max_items:
                return items
        if not items:
            break
    return items


def _item_from_html(html: str, *, place: str, mode: str, source_url: str) -> dict[str, Any]:
    item: dict[str, Any] = {"source_url": source_url, "confidence": 0.52}
    title_match = _TITLE_RE.search(html)
    if title_match:
        item["review_summary"] = title_match.group(1).strip()[:300]
    crowd = _CROWD_RE.search(html)
    if crowd:
        item["crowd_risk"] = crowd.group(0)
    if mode == "ticket":
        tickets = _TICKET_RE.findall(html)
        if tickets:
            item["ticket_related_mentions"] = tickets[:3]
    if mode == "guide":
        season = _SEASON_RE.search(html)
        if season:
            item["seasonality"] = season.group(0)
            item["best_time_to_visit"] = season.group(0)
    if not item.get("review_summary"):
        item["review_summary"] = f"携程 {place} 页面信号"
    return item


def run_query(place: str, city: str | None, mode: str, max_results: int) -> dict[str, Any]:
    try:
        sight_url, sight_title = _search_sight_url(place, city)
    except Exception as exc:
        return {"items": [], "error": str(exc)}
    if not sight_url:
        return {"items": [], "error": f"ctrip sight search returned no url for {place}"}

    items: list[dict[str, Any]] = []
    resource_id = _resource_id_from_url(sight_url)
    if mode in {"review", "ticket", "crowd"} and resource_id:
        items = _comments_via_vendor(resource_id, max_items=max_results)

    if not items:
        try:
            html = fetch_text(sight_url)
        except Exception as exc:
            return {"items": [], "error": str(exc)}
        item = _item_from_html(html, place=place, mode=mode, source_url=sight_url)
        if sight_title:
            item.setdefault("review_summary", sight_title)
        items = [item]

    return {"items": items[:max_results]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ctrip vendor place query adapter")
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
