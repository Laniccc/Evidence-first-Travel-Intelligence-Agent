from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.client_manager import MCPClientManager, MCPInvokeResult, get_mcp_client_manager

logger = logging.getLogger(__name__)

_OPENING_SNIPPET = re.compile(
    r"开放|通车|封路|几月|月份|\d{1,2}月",
    re.I,
)
_OFFICIAL_DOMAIN_HINTS = (
    ".gov",
    ".gov.cn",
    ".edu",
    "tourism",
    "travel",
    "景区",
    "official",
    "ticket",
    "ctrip.com/spot",
)


class SearchMCPAdapter(BaseTravelTool):
    """open-webSearch HTTP adapter — converts web search hits into Evidence summaries."""

    name = "search_mcp"
    policy_name = "search_mcp"
    server_name = "search"

    def __init__(self, client: MCPClientManager | None = None) -> None:
        self._client = client or get_mcp_client_manager()

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

        limit = int(kwargs.get("limit") or 5)
        result: MCPInvokeResult = await self._client.open_websearch_search(
            str(query),
            limit=limit,
            server_name=self.server_name,
        )
        if not result.ok:
            raise RuntimeError(result.error or "open-webSearch search failed")

        return self._hits_to_evidence(
            result.data,
            query=str(query),
            country=kwargs.get("country"),
            city=kwargs.get("city"),
            place_name=kwargs.get("place_name"),
            information_need=kwargs.get("information_need") or kwargs.get("need_type"),
        )

    def _hits_to_evidence(
        self,
        raw: Any,
        *,
        query: str,
        country: str | None,
        city: str | None,
        place_name: str | None,
        information_need: str | None,
    ) -> list[Evidence]:
        hits = self._extract_hits(raw)
        if not hits:
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
                    limitations=[
                        "open-webSearch returned no results.",
                        "Search summary only; official page read not performed.",
                    ],
                )
            ]

        evidence_list: list[Evidence] = []
        for hit in hits[:8]:
            title = str(hit.get("title") or hit.get("name") or "").strip()
            url = str(hit.get("url") or hit.get("link") or "").strip() or None
            snippet = str(hit.get("snippet") or hit.get("description") or hit.get("content") or "").strip()
            if not title and not snippet:
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
                ticketish = re.search(r"门票|票价|收费|免费|元", f"{title} {snippet}", re.I)
                if officialish:
                    claim_type = ClaimType.TICKET_PRICE
                    confidence = 0.55
                elif ticketish:
                    claim_type = ClaimType.TICKET_PRICE_CANDIDATE
                    confidence = 0.48

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
        blob = f"{url or ''} {title} {snippet}".lower()
        if any(hint in blob for hint in _OFFICIAL_DOMAIN_HINTS):
            return True
        if url:
            host = (urlparse(url).hostname or "").lower()
            if host.endswith(".gov.cn") or host.endswith(".gov"):
                return True
        return bool(re.search(r"官方|门票|票价|景区官网", f"{title} {snippet}"))
