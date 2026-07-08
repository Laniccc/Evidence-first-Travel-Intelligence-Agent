from __future__ import annotations

from datetime import datetime

from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


class WikipediaMCPAdapter(BaseTravelTool):
    name = "wikipedia_mcp"
    policy_name = "wikipedia_mcp"
    server_name = "wikipedia"

    def __init__(self, client: MCPClientManager | None = None) -> None:
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("wikipedia")

    async def run(self, **kwargs) -> list[Evidence]:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("wikipedia"))

        query = kwargs.get("query") or kwargs.get("place_name") or ""
        if not query:
            raise ValueError("wikipedia_mcp requires query")

        country = (kwargs.get("country") or "").lower()
        language = kwargs.get("language") or ("zh" if "china" in country else "en")

        search = await self._client.invoke(
            "wikipedia",
            "wikipedia_search",
            {"query": str(query), "language": language, "limit": 3},
        )
        if not search.ok:
            raise RuntimeError(search.error or "wikipedia_search failed")

        title = self._first_title(search.data) or str(query)
        summary = await self._client.invoke(
            "wikipedia",
            "wikipedia_get_summary",
            {"title": title, "language": language},
        )
        if not summary.ok:
            raise RuntimeError(summary.error or "wikipedia_get_summary failed")

        text = text_from_mcp_payload(summary.data)
        claim_type = self._claim_type_for_need(kwargs.get("information_need"))
        return [
            Evidence(
                source_name="Wikipedia MCP",
                source_type=SourceType.WEB,
                source_url=f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}" if title else None,
                country=kwargs.get("country") or "Unknown",
                city=kwargs.get("city"),
                place_name=kwargs.get("place_name"),
                retrieved_at=datetime.utcnow(),
                data_freshness=DataFreshness.STALE,
                license_scope=LicenseScope.PUBLIC_PAGE,
                confidence=0.7,
                claims=[
                    Claim(
                        claim_type=claim_type,
                        value=text[:600],
                        raw_text=text[:2000],
                        confidence=0.7,
                        normalized_value={"title": title, "language": language},
                    )
                ],
                limitations=["Wikipedia summary; verify critical facts."],
            )
        ]

    @staticmethod
    def _claim_type_for_need(information_need: str | None) -> ClaimType:
        """Map information need to appropriate claim type for Wikipedia results."""
        if not information_need:
            return ClaimType.TRAVEL_ADVICE
        need = str(information_need).lower()
        if need in ("elevation", "altitude", "height", "海拔"):
            return ClaimType.ELEVATION
        if need in ("general_fact", "fact_lookup", "fact"):
            return ClaimType.GENERAL_FACT
        return ClaimType.TRAVEL_ADVICE

    @staticmethod
    def _first_title(data) -> str | None:
        if isinstance(data, dict):
            for key in ("results", "items"):
                bucket = data.get(key)
                if isinstance(bucket, list) and bucket:
                    first = bucket[0]
                    if isinstance(first, dict):
                        return str(first.get("title") or first.get("name") or "")
        return None
