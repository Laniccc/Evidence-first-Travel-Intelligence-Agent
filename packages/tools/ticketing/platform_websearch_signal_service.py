"""Built-in Ctrip/Dianping review & ticket signals via open-webSearch (no external CLI)."""

from __future__ import annotations

import re
from typing import Any, Literal

from app.config import Settings, get_settings
from tools.mcp.adapters.search_mcp_adapter import SearchMCPAdapter
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager

PlatformName = Literal["ctrip", "dianping"]

_PRICE_RE = re.compile(r"[¥￥]\s*\d+(?:\.\d+)?(?:\s*起)?|\d+(?:\.\d+)?\s*元")
_TICKET_RE = re.compile(
    r"门票|票价|预约|团购|套票|成人票|儿童票|购票|收费|免票|半价|索道|缆车|进山|进山费"
)
_CROWD_RE = re.compile(r"排队|人多|拥挤|人少|清净")
_VALUE_RE = re.compile(r"性价比|值得|不值|贵|便宜")
_POI_URL_RE = {
    "ctrip": re.compile(r"you\.ctrip\.com/sight", re.I),
    "dianping": re.compile(r"dianping\.com/(?:shop|poi)", re.I),
}

_PLATFORM_DOMAINS = {
    "ctrip": ("ctrip.com", "携程"),
    "dianping": ("dianping.com", "大众点评"),
}


class PlatformWebSearchSignalService:
    """Query platform-biased web search and normalize hits to crawler item shape."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: MCPClientManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client or get_mcp_client_manager()
        self.last_run_meta: dict[str, Any] = {}

    def is_available(self) -> bool:
        return bool(
            self.settings.mcp_search_enabled
            and self._client.is_server_configured("search")
        )

    @staticmethod
    def _place_keyword(place_name: str, query: str | None) -> str:
        place = (place_name or "").strip()
        if place:
            return place
        return (query or "").strip()

    def _queries(
        self,
        platform: PlatformName,
        place_name: str,
        city: str | None,
        *,
        ticket_focus: bool,
        query: str | None,
        include_brand_only: bool = False,
    ) -> list[str]:
        domain, brand = _PLATFORM_DOMAINS[platform]
        anchor = self._place_keyword(place_name, query)
        city_part = (city or "").strip()
        location = f"{city_part} {anchor}".strip() if city_part else anchor
        if ticket_focus:
            base = [
                f"site:{domain} {location} 门票 票价",
                f"{brand} {location} 门票",
                f"{location} {brand} 票价",
            ]
            if include_brand_only:
                base.extend(
                    [
                        f"{brand} {location} 门票 票价",
                        f"{location} 门票 {brand}",
                    ]
                )
        else:
            base = [
                f"site:{domain} {location} 评价 游玩",
                f"{brand} {location} 点评",
                f"{location} {brand} 评价",
            ]
            if include_brand_only:
                base.append(f"{brand} {location} 评价")
        return base

    @staticmethod
    def _search_error_from_result(result: Any) -> str | None:
        meta = getattr(result, "meta", None) or {}
        messages = meta.get("partial_failure_messages") or []
        if messages:
            return "search engine failed: " + "; ".join(str(m) for m in messages[:2])
        partial = meta.get("partial_failures") or []
        if partial:
            from tools.mcp.client_manager import MCPClientManager

            formatted = [
                MCPClientManager.format_partial_failure(f)
                for f in partial[:2]
                if isinstance(f, dict)
            ]
            if formatted:
                return "search engine failed: " + "; ".join(formatted)
        return None

    async def fetch_signal_items(
        self,
        platform: PlatformName,
        place_name: str,
        city: str | None = None,
        *,
        query: str | None = None,
        ticket_focus: bool = False,
        max_results: int | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.is_available():
            return [], "open-webSearch (search MCP) not configured"
        limit = max_results or 10
        queries = self._queries(
            platform,
            place_name,
            city,
            ticket_focus=ticket_focus,
            query=query,
        )
        items: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        errors: list[str] = []
        raw_hit_count = 0
        filtered_hit_count = 0
        partial_failures: list[Any] = []
        engines_tried: list[str] = []

        async def _run_queries(query_list: list[str]) -> bool:
            nonlocal raw_hit_count, filtered_hit_count
            for search_q in query_list:
                result = await self._client.open_websearch_search(search_q, limit=5)
                if result.meta:
                    engines_tried.extend(result.meta.get("engines_tried") or [])
                    partial_failures.extend(result.meta.get("partial_failures") or [])
                if not result.ok:
                    errors.append(result.error or f"search failed: {search_q[:48]}")
                    continue
                hits = SearchMCPAdapter._extract_hits(result.data)
                if not hits:
                    engine_err = self._search_error_from_result(result)
                    if engine_err:
                        errors.append(engine_err)
                    else:
                        errors.append(f"search returned no hits: {search_q[:48]}")
                    continue
                raw_hit_count += len(hits)
                for hit in hits:
                    item = self._hit_to_item(hit, platform=platform, ticket_focus=ticket_focus)
                    if not item:
                        filtered_hit_count += 1
                        continue
                    url = str(item.get("source_url") or "")
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    items.append(item)
                    if len(items) >= limit:
                        return True
                if len(items) >= limit:
                    return True
            return len(items) >= limit

        await _run_queries(queries)
        if not items and ticket_focus:
            brand_queries = self._queries(
                platform,
                place_name,
                city,
                ticket_focus=ticket_focus,
                query=query,
                include_brand_only=True,
            )
            extra = [q for q in brand_queries if q not in queries]
            if extra:
                await _run_queries(extra)

        if not items:
            domain, brand = _PLATFORM_DOMAINS[platform]
            anchor = self._place_keyword(place_name, query)
            city_part = (city or "").strip()
            location = f"{city_part} {anchor}".strip() if city_part else anchor
            relaxed = [
                f"{brand} {location} 门票 价格",
                f"{location} 门票 {brand}",
                f"{location} 门票 票价",
            ]
            if ticket_focus:
                relaxed.append(f"{location} 门票")
            await _run_queries([q for q in relaxed if q not in queries])

        unique_engines = list(dict.fromkeys(engines_tried))
        self.last_run_meta = {
            "transport": "platform_websearch",
            "platform": platform,
            "queries": queries,
            "item_count": len(items),
            "raw_hit_count": raw_hit_count,
            "filtered_hit_count": filtered_hit_count,
            "partial_failures": partial_failures[:5] if partial_failures else None,
            "engines_tried": unique_engines or None,
            "errors": errors[:3] if errors else None,
        }
        if not items:
            if partial_failures or any("search engine failed" in e for e in errors):
                detail = "; ".join(errors[:2]) if errors else "search engine error"
                return [], (
                    f"{_PLATFORM_DOMAINS[platform][1]} websearch failed: {detail}"
                )
            if raw_hit_count > 0 and filtered_hit_count > 0:
                return [], (
                    f"{_PLATFORM_DOMAINS[platform][1]} websearch returned no signal items "
                    f"(hits filtered by ticket_focus: {raw_hit_count} raw, 0 kept)"
                )
            detail = "; ".join(errors[:2]) if errors else "no platform-biased search hits"
            return [], (
                f"{_PLATFORM_DOMAINS[platform][1]} websearch returned no signal items ({detail})"
            )
        return items, None

    @staticmethod
    def _is_platform_poi_url(platform: PlatformName, url: str | None) -> bool:
        if not url:
            return False
        pattern = _POI_URL_RE.get(platform)
        return bool(pattern and pattern.search(url))

    @staticmethod
    def _hit_to_item(
        hit: dict[str, Any],
        *,
        platform: PlatformName,
        ticket_focus: bool,
    ) -> dict[str, Any] | None:
        title = str(hit.get("title") or hit.get("name") or "").strip()
        url = str(hit.get("url") or hit.get("link") or "").strip() or None
        snippet = str(hit.get("snippet") or hit.get("description") or hit.get("content") or "").strip()
        blob = f"{title} {snippet}".strip()
        if not blob:
            return None

        prices = _PRICE_RE.findall(blob)
        ticket_bits = [m.group(0) for m in _TICKET_RE.finditer(blob)]
        on_poi_page = PlatformWebSearchSignalService._is_platform_poi_url(platform, url)

        item: dict[str, Any] = {
            "review_summary": blob[:500],
            "source_url": url,
            "confidence": 0.58 if url and _PLATFORM_DOMAINS[platform][0] in (url or "").lower() else 0.52,
        }

        if prices:
            item["price_text"] = prices[0]
            item["ticket_related_mentions"] = prices[:3]

        if ticket_bits:
            mentions = item.setdefault("ticket_related_mentions", [])
            if isinstance(mentions, list):
                for bit in ticket_bits[:3]:
                    if bit not in mentions:
                        mentions.append(bit)

        if ticket_focus and on_poi_page and not item.get("price_text") and not item.get("ticket_related_mentions"):
            item["confidence"] = 0.48
            item["ticket_related_mentions"] = ["platform_poi_page"]

        crowd = _CROWD_RE.search(blob)
        if crowd:
            item["crowd_risk"] = crowd.group(0)
        if _VALUE_RE.search(blob):
            item["value_for_money"] = blob[:120]

        brand = _PLATFORM_DOMAINS[platform][1]
        if (
            ticket_focus
            and platform == "dianping"
            and not on_poi_page
            and (brand in blob or "点评" in blob)
            and (_PRICE_RE.search(blob) or ticket_bits)
        ):
            item["confidence"] = min(float(item.get("confidence") or 0.52), 0.54)
            return item

        if ticket_focus and not item.get("price_text") and not item.get("ticket_related_mentions"):
            return None
        return item
