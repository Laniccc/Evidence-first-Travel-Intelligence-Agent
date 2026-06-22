from __future__ import annotations

from typing import Any

from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import (
    build_page_evidence,
    pick_url_from_evidence,
    text_from_mcp_payload,
)
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


class OfficialPageFetchAdapter(BaseTravelTool):
    """Fetch official page via open-webSearch /fetch-web and extract structured claims."""

    name = "official_page_reader_mcp"
    policy_name = "official_page_reader_mcp"
    server_name = "search"

    def __init__(self, client: MCPClientManager | None = None) -> None:
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("search")

    async def run(self, **kwargs) -> list:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("search"))

        url = (kwargs.get("url") or kwargs.get("source_url") or "").strip()
        if not url:
            prior = kwargs.get("prior_evidence") or kwargs.get("evidence") or []
            if isinstance(prior, list):
                url = pick_url_from_evidence(prior) or ""
        if not url:
            raise ValueError("official_page_reader_mcp requires url (from search_mcp or kwargs)")

        result = await self._client.open_websearch_fetch(url, server_name="search")
        if not result.ok:
            raise RuntimeError(result.error or "fetch-web failed")

        text = text_from_mcp_payload(result.data)
        if not text.strip():
            raise RuntimeError("fetch-web returned empty content")

        ev = build_page_evidence(
            source_name="Official Page (fetch-web)",
            source_url=url,
            text=text,
            country=kwargs.get("country"),
            city=kwargs.get("city"),
            place_name=kwargs.get("place_name"),
            information_need=kwargs.get("information_need") or kwargs.get("need_type"),
            limitations_extra=["Fetched via open-webSearch /fetch-web."],
        )
        return [ev]
