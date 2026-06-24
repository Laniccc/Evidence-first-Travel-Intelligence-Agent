from __future__ import annotations

from typing import Any

from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import (
    build_page_evidence,
    extract_claims_from_text,
    pick_url_from_evidence,
    text_from_mcp_payload,
)
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager
from tools.official_source.official_page_follower import claims_satisfy_need, plan_follow_urls


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
            from tools.official_source.whitelist_resolver import resolve_official_whitelist_url

            place = str(kwargs.get("place_name") or "").strip()
            url = resolve_official_whitelist_url(place) or ""
        if not url:
            query = (
                kwargs.get("query")
                or kwargs.get("place_name")
                or ""
            ).strip()
            need = kwargs.get("information_need") or kwargs.get("need_type") or ""
            if query and need == "ticket_price" and "门票" not in query:
                query = f"{query} 官网 门票"
            elif query and "官网" not in query:
                query = f"{query} 官网"
            if query:
                search = await self._client.open_websearch_search(str(query), limit=5)
                if search.ok:
                    prior_hits = kwargs.get("prior_evidence") or []
                    if isinstance(prior_hits, list):
                        url = pick_url_from_evidence(prior_hits) or ""
                    if not url and isinstance(search.data, dict):
                        results = search.data.get("data", search.data)
                        if isinstance(results, dict):
                            results = results.get("results", results.get("hits", []))
                        if isinstance(results, list):
                            for hit in results:
                                if not isinstance(hit, dict):
                                    continue
                                candidate = str(hit.get("url") or hit.get("link") or "").strip()
                                if candidate:
                                    url = candidate
                                    break
        if not url:
            raise ValueError("official_page_reader_mcp requires url (from search_mcp or kwargs)")

        information_need = kwargs.get("information_need") or kwargs.get("need_type")
        place_name = kwargs.get("place_name")
        limitations_extra = ["Fetched via open-webSearch /fetch-web."]

        first_text = await self._fetch_page_text(url)
        follow_urls = plan_follow_urls(
            url,
            information_need=information_need,
            page_html=first_text,
            place_name=place_name,
            max_urls=int(kwargs.get("max_follow_urls") or 4),
        )
        urls_to_try = [url, *follow_urls]

        last_text = first_text
        last_url = url
        for page_url in urls_to_try:
            text = first_text if page_url == url else await self._fetch_page_text(page_url)
            last_text = text
            last_url = page_url
            claims, _ = extract_claims_from_text(text, information_need=information_need)
            if claims_satisfy_need(claims, information_need):
                if page_url != url:
                    limitations_extra.append(f"Followed official subpage: {page_url}")
                return [
                    build_page_evidence(
                        source_name="Official Page (fetch-web)",
                        source_url=page_url,
                        text=text,
                        country=kwargs.get("country"),
                        city=kwargs.get("city"),
                        place_name=place_name,
                        information_need=information_need,
                        limitations_extra=list(limitations_extra),
                    )
                ]

        if not last_text.strip():
            raise RuntimeError("fetch-web returned empty content")

        if follow_urls:
            limitations_extra.append(
                f"Tried official subpages ({', '.join(follow_urls[:3])}) without structured {information_need}."
            )
        return [
            build_page_evidence(
                source_name="Official Page (fetch-web)",
                source_url=last_url,
                text=last_text,
                country=kwargs.get("country"),
                city=kwargs.get("city"),
                place_name=place_name,
                information_need=information_need,
                limitations_extra=limitations_extra,
            )
        ]

    async def _fetch_page_text(self, url: str) -> str:
        result = await self._client.open_websearch_fetch(
            url,
            server_name="search",
            max_chars=250_000,
        )
        if not result.ok:
            raise RuntimeError(result.error or "fetch-web failed")
        text = text_from_mcp_payload(result.data)
        if isinstance(result.data, dict) and result.data.get("truncated"):
            text = await self._fetch_page_text_direct(url)
        elif text.strip().startswith('{"truncated"'):
            text = await self._fetch_page_text_direct(url)
        elif not text.strip():
            raise RuntimeError("fetch-web returned empty content")
        return text

    @staticmethod
    async def _fetch_page_text_direct(url: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            body = response.text
        if not body.strip():
            raise RuntimeError("direct fetch returned empty content")
        return body
