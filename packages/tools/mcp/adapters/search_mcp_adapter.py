from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.client_manager import MCPClientManager, MCPInvokeResult, get_mcp_client_manager
from tools.ticket_price_text import has_explicit_ticket_price_signal

logger = logging.getLogger(__name__)

_OPENING_SNIPPET = re.compile(
    r"开放|通车|封路|几月|月份|\d{1,2}月",
    re.I,
)
_ELEVATION_SNIPPET = re.compile(r"海拔|高度|elevation|altitude", re.I)
_ELEVATION_VALUE = re.compile(
    r"(?:海拔|高度|海拔约|高度约)[约为]?\s*(\d{3,5})\s*米",
    re.I,
)
_ELEVATION_NEEDS = frozenset({"elevation", "altitude", "height", "海拔"})
_OFFICIAL_DOMAIN_HINTS = (
    ".gov",
    ".gov.cn",
    ".edu",
    "tourism",
    "travel",
    "official",
)

_SPAM_DOMAINS = frozenset({
    "17173.com", "weixin.qq.com", "chsi.com.cn", "gaokao.chsi.com.cn",
})

_SPAM_TITLE_SIGNALS = (
    "17173", "游戏", "萌妹", "少女兔", "阳光高考",
    "强基计划", "考研", "高考",
)


class SearchMCPAdapter(BaseTravelTool):
    """open-webSearch HTTP adapter — converts web search hits into Evidence summaries."""

    name = "search_mcp"
    policy_name = "search_mcp"
    server_name = "search"

    def __init__(self, client: MCPClientManager | None = None) -> None:
        self._client = client or get_mcp_client_manager()
        self.last_run_meta: dict[str, Any] = {}

    @staticmethod
    def resolve_search_limit(kwargs: dict[str, Any]) -> int:
        """Resolve top_k / max_results / limit — default and floor at 5."""
        candidates = [
            int(kwargs.get("top_k") or 0),
            int(kwargs.get("max_results") or 0),
            int(kwargs.get("limit") or 0),
        ]
        return max(max(candidates, default=0), 5)

    def is_available(self) -> bool:
        return self._client.is_server_configured(self.server_name)

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason(self.server_name))

        query = (
            kwargs.get("query")
            or kwargs.get("q")
            or kwargs.get("place_name")
            or ""
        )
        if not query:
            raise ValueError("search_mcp requires query")

        self.last_run_meta = {}
        limit = self.resolve_search_limit(kwargs)
        result: MCPInvokeResult = await self._client.open_websearch_search(
            str(query),
            limit=limit,
            server_name=self.server_name,
        )
        if not result.ok:
            raise RuntimeError(result.error or "open-webSearch search failed")

        evidence = self._hits_to_evidence(
            result.data,
            query=str(query),
            country=kwargs.get("country"),
            city=kwargs.get("city"),
            place_name=kwargs.get("place_name"),
            information_need=kwargs.get("information_need") or kwargs.get("need_type"),
            search_meta=result.meta,
        )
        if self.last_run_meta.get("kept_result_count", 0) <= 1:
            self.last_run_meta.setdefault("filter_reason", self.last_run_meta.get("filter_reason") or "none")
        return evidence

    def _hits_to_evidence(
        self,
        raw: Any,
        *,
        query: str,
        country: str | None,
        city: str | None,
        place_name: str | None,
        information_need: str | None,
        search_meta: dict[str, Any] | None = None,
    ) -> list[Evidence]:
        hits = self._extract_hits(raw)
        raw_count = len(hits)
        filter_tally: dict[str, int] = {}

        def _filter(reason: str) -> None:
            filter_tally[reason] = filter_tally.get(reason, 0) + 1

        if not hits:
            self.last_run_meta.update(
                {
                    "raw_result_count": 0,
                    "kept_result_count": 0,
                    "filtered_result_count": 0,
                    "filter_reason": "no_hits",
                }
            )
            limitations = [
                "open-webSearch returned no results.",
                "Search summary only; official page read not performed.",
            ]
            failure_messages = (search_meta or {}).get("partial_failure_messages") or []
            if failure_messages:
                limitations.insert(
                    0,
                    "Search engine error: " + "; ".join(str(m) for m in failure_messages[:3]),
                )
            elif (search_meta or {}).get("partial_failures"):
                from tools.mcp.client_manager import MCPClientManager

                partial = search_meta.get("partial_failures") or []
                formatted = [
                    MCPClientManager.format_partial_failure(f)
                    for f in partial[:3]
                    if isinstance(f, dict)
                ]
                if formatted:
                    limitations.insert(0, "Search engine error: " + "; ".join(formatted))
            return [
                Evidence(
                    source_name="open-webSearch",
                    source_type=SourceType.WEB,
                    source_url=None,
                    country=country or "Unknown",
                    city=city,
                    place_name=place_name,
                    retrieved_at=datetime.utcnow(),
                    data_freshness=DataFreshness.RECENT,
                    license_scope=LicenseScope.PUBLIC_PAGE,
                    confidence=0.4,
                    claims=[
                        Claim(
                            claim_type=ClaimType.TRAVEL_ADVICE,
                            value=f"No search hits for: {query}",
                            raw_text=f"No search hits for: {query}",
                            confidence=0.35,
                        )
                    ],
                    limitations=limitations,
                )
            ]

        # Build relevance anchors from place context
        relevance_anchors = self._build_relevance_anchors(
            query=query,
            place_name=place_name,
            city=city,
        )

        evidence_list: list[Evidence] = []
        for hit in hits[:12]:
            title = str(hit.get("title") or hit.get("name") or "").strip()
            url = str(hit.get("url") or hit.get("link") or "").strip() or None
            snippet = str(hit.get("snippet") or hit.get("description") or hit.get("content") or "").strip()
            if not title and not snippet:
                _filter("empty")
                continue

            # Filter out obvious spam / off-topic results
            if self._is_spam(title, snippet, url):
                logger.debug("search_mcp: filtered spam result title=%r engine=%r",
                             title[:80], hit.get("engine", "?"))
                _filter("spam")
                continue

            # Filter results clearly unrelated to the queried place
            if relevance_anchors and not self._is_relevant(title, snippet, relevance_anchors):
                logger.debug("search_mcp: filtered irrelevant result title=%r", title[:80])
                _filter("irrelevant")
                continue

            officialish = self._looks_official(url, title, snippet)
            confidence = 0.62 if officialish else 0.5
            claim_type = ClaimType.TRAVEL_ADVICE

            if information_need in {"seasonal_operation_status", "road_opening_period"}:
                if _OPENING_SNIPPET.search(f"{title} {snippet}"):
                    claim_type = ClaimType.SEASONAL_OPERATION_STATUS
                    confidence = 0.68 if officialish else 0.58
                elif officialish:
                    claim_type = ClaimType.ROAD_OPENING_PERIOD
                    confidence = 0.55
            elif information_need == "ticket_price":
                text = f"{title} {snippet}"
                ticketish = re.search(r"门票|票价|收费|免费|免票|元|¥|￥", text, re.I)
                has_price = has_explicit_ticket_price_signal(text)
                if self._is_low_value_ticket_search_hit(title, snippet, url, has_price=has_price):
                    _filter("low_value_ticket")
                    continue
                if officialish and has_price:
                    claim_type = ClaimType.TICKET_PRICE
                    confidence = 0.55
                elif has_price:
                    claim_type = ClaimType.TICKET_PRICE_CANDIDATE
                    confidence = 0.48
                elif ticketish:
                    claim_type = ClaimType.TICKET_RELATED_MENTIONS
                    confidence = 0.42
            elif information_need in _ELEVATION_NEEDS:
                text = f"{title} {snippet}"
                if _ELEVATION_SNIPPET.search(text):
                    claim_type = ClaimType.ELEVATION
                    match = _ELEVATION_VALUE.search(text)
                    if match:
                        confidence = 0.62 if officialish else 0.52
                    else:
                        confidence = 0.55 if officialish else 0.45

            summary = title
            if snippet:
                summary = f"{title}: {snippet}" if title else snippet

            evidence_list.append(
                Evidence(
                    source_name="open-webSearch",
                    source_type=SourceType.WEB,
                    source_url=url,
                    country=country or "Unknown",
                    city=city,
                    place_name=place_name,
                    retrieved_at=datetime.utcnow(),
                    data_freshness=DataFreshness.RECENT,
                    license_scope=LicenseScope.PUBLIC_PAGE,
                    confidence=confidence,
                    claims=[
                        Claim(
                            claim_type=claim_type,
                            value=summary[:500],
                            raw_text=summary[:1200],
                            normalized_value=url,
                            confidence=confidence,
                            metadata={"title": title, "url": url, "snippet": snippet[:400]},
                        )
                    ],
                    limitations=[
                        "Search result summary only; price not verified on official page.",
                        "Use browser_mcp / official_page_reader_mcp to confirm hard facts.",
                    ],
                )
            )

        kept = len(evidence_list)
        filtered = raw_count - kept
        reason = ", ".join(f"{k}:{v}" for k, v in sorted(filter_tally.items())) if filter_tally else "none"
        self.last_run_meta.update(
            {
                "raw_result_count": raw_count,
                "kept_result_count": kept,
                "filtered_result_count": filtered,
                "filter_reason": reason,
            }
        )
        return evidence_list

    @staticmethod
    def _extract_hits(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return [h for h in raw if isinstance(h, dict)]
        if not isinstance(raw, dict):
            return []
        for key in ("results", "items", "hits"):
            bucket = raw.get(key)
            if isinstance(bucket, list):
                return [h for h in bucket if isinstance(h, dict)]
        nested = raw.get("data")
        if isinstance(nested, dict):
            for key in ("results", "items", "hits"):
                bucket = nested.get(key)
                if isinstance(bucket, list):
                    return [h for h in bucket if isinstance(h, dict)]
        if isinstance(nested, list):
            return [h for h in nested if isinstance(h, dict)]
        return []

    @staticmethod
    def _looks_official(url: str | None, title: str, snippet: str) -> bool:
        if url:
            host = (urlparse(url).hostname or "").lower()
            if host in {"sogou.com", "www.sogou.com", "baidu.com", "www.baidu.com", "bing.com", "www.bing.com"}:
                return False
            if host.endswith(".gov.cn") or host.endswith(".gov"):
                return True
        blob = f"{url or ''} {title} {snippet}".lower()
        if any(hint in blob for hint in _OFFICIAL_DOMAIN_HINTS):
            return True
        return bool(re.search(r"官方|官网|政府|文旅|旅游局|景区官网", f"{title} {snippet}"))

    @staticmethod
    def _build_relevance_anchors(
        query: str,
        place_name: str | None,
        city: str | None,
    ) -> list[str]:
        """Build tokens that search results should contain to be considered relevant."""
        anchors: list[str] = []
        if place_name:
            anchors.append(place_name)
        if city:
            anchors.append(city)
        # Extract Chinese tokens from query as extra anchors
        cn_tokens = re.findall(r"[一-鿿]{2,6}", str(query))
        for t in cn_tokens[:3]:
            if t not in anchors:
                anchors.append(t)
        return anchors

    @staticmethod
    def _is_relevant(title: str, snippet: str, anchors: list[str]) -> bool:
        """Check if a search hit is plausibly about the queried place.

        When a concrete place is known, prefer the exact place anchor. Falling
        back to city+alias avoids broad homonym matches such as 栖霞山 vs 山东栖霞.
        Without anchors, default to True (can't filter).
        """
        if not anchors:
            return True
        blob = f"{title} {snippet}"
        primary = anchors[0] if anchors else ""
        city = anchors[1] if len(anchors) > 1 else ""
        generic = {"门票", "票价", "价格", "官网", "官方", "景区", "预约", "购票", "多少钱"}
        if primary and primary in blob:
            return True
        if primary:
            aliases = [a for a in anchors[2:] if a and a != primary and a not in generic]
            if not aliases:
                return False
            if city:
                return bool(city in blob and any(alias in blob for alias in aliases))
            return any(alias in blob for alias in aliases)
        return any(anchor in blob for anchor in anchors)

    @staticmethod
    def _is_spam(title: str, snippet: str, url: str | None) -> bool:
        """Detect search results that are clearly spam, gaming, or off-topic content.

        Uses a combination of domain blocklist and title signal matching.
        Only flags results with strong spam indicators to avoid over-filtering.
        """
        # Domain blocklist check
        if url:
            host = (urlparse(url).hostname or "").lower()
            # Check exact domain match
            if host in _SPAM_DOMAINS:
                return True
            # Check subdomain match
            for spam_domain in _SPAM_DOMAINS:
                if host.endswith("." + spam_domain) or host == spam_domain:
                    return True

        # Title signal check: multiple spam signals = spam
        blob = f"{title} {snippet}".lower()
        signal_count = sum(1 for s in _SPAM_TITLE_SIGNALS if s.lower() in blob)
        return signal_count >= 2

    @staticmethod
    def _is_low_value_ticket_search_hit(title: str, snippet: str, url: str | None, *, has_price: bool) -> bool:
        """Drop broad travel articles that only mention tickets in passing."""
        if has_price:
            return False
        blob = f"{title} {snippet}".lower()
        host = (urlparse(url).hostname or "").lower() if url else ""
        low_value_domains = {"zhihu.com", "zhuanlan.zhihu.com", "sohu.com", "baike.baidu.com"}
        if host in low_value_domains or any(host.endswith("." + d) for d in low_value_domains):
            return True
        if re.search(r"攻略|游记|值得去|怎么玩|景点推荐|旅游景区|知乎|zhuanlan", blob, re.I):
            if not re.search(r"官方购票|购票入口|优惠政策|半票|免票|收费标准|成人票|儿童票|学生票", blob, re.I):
                return True
        return False
