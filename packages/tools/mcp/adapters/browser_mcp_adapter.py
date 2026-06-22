from __future__ import annotations

from tools.base import BaseTravelTool
from tools.mcp.adapters.page_content_extractor import build_page_evidence, text_from_mcp_payload
from tools.mcp.client_manager import MCPClientManager, get_mcp_client_manager


class BrowserMCPAdapter(BaseTravelTool):
    """Playwright MCP: browser_navigate + browser_snapshot → Evidence."""

    name = "browser_mcp"
    policy_name = "browser_mcp"
    server_name = "browser"

    def __init__(self, client: MCPClientManager | None = None) -> None:
        self._client = client or get_mcp_client_manager()

    def is_available(self) -> bool:
        return self._client.is_server_configured("browser")

    async def run(self, **kwargs) -> list:
        if not self.is_available():
            raise RuntimeError(self._client.server_block_reason("browser"))

        url = (kwargs.get("url") or kwargs.get("source_url") or "").strip()
        if not url:
            query = kwargs.get("query") or kwargs.get("place_name") or ""
            if query:
                search = await self._client.open_websearch_search(str(query), limit=3)
                if search.ok and isinstance(search.data, dict):
                    results = search.data.get("data", search.data).get("results", [])
                    if isinstance(results, list) and results:
                        url = str(results[0].get("url") or "")
        if not url:
            raise ValueError("browser_mcp requires url or resolvable query")

        nav = await self._client.invoke("browser", "browser_navigate", {"url": url})
        if not nav.ok:
            raise RuntimeError(nav.error or "browser_navigate failed")

        snap = await self._client.invoke("browser", "browser_snapshot", {})
        if not snap.ok:
            raise RuntimeError(snap.error or "browser_snapshot failed")

        text = text_from_mcp_payload(snap.data)
        ev = build_page_evidence(
            source_name="Playwright MCP",
            source_url=url,
            text=text,
            country=kwargs.get("country"),
            city=kwargs.get("city"),
            place_name=kwargs.get("place_name"),
            information_need=kwargs.get("information_need") or kwargs.get("need_type"),
            limitations_extra=["Read via Playwright browser_snapshot."],
        )
        return [ev]
