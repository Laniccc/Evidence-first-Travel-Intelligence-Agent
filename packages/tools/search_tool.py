"""Simple web search tool using MCP open-websearch or HTTP fallback."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SearchTool:
    """Async web search tool. Tries MCP open-websearch first, falls back to direct HTTP."""

    def __init__(self, server_url: str = "http://127.0.0.1:3210", timeout: float = 30.0):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

    async def search(self, query: str, limit: int = 5, engine: str = "baidu") -> list[dict[str, Any]]:
        """Execute a web search and return results."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.server_url}/search",
                    json={"query": query, "limit": limit, "engines": [engine]},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("data", {}).get("results", [])
                    logger.info("Search '%s': %d results", query[:50], len(results))
                    return results
                logger.warning("Search returned %d: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Search failed for '%s': %s", query[:50], e)
        return []

    async def fetch_web(self, url: str, timeout: int = 15000) -> str | None:
        """Fetch a web page content."""
        try:
            async with httpx.AsyncClient(timeout=min(timeout / 1000.0, 30.0)) as client:
                resp = await client.post(
                    f"{self.server_url}/fetch-web",
                    json={"url": url, "timeout": timeout},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get("data", {}).get("content", "")
                    if content and len(content) > 50:
                        return content
        except Exception as e:
            logger.warning("Fetch failed for '%s': %s", url[:60], e)
        return None


class ToolRegistry:
    """Minimal tool registry that wraps SearchTool for the agent phases."""

    def __init__(self, search_tool: SearchTool | None = None):
        self.search_tool = search_tool or SearchTool()

    async def run_tool(self, tool_name: str, **kwargs: Any) -> Any:
        if tool_name == "search":
            query = kwargs.get("query", "")
            limit = kwargs.get("limit", 5)
            return await self.search_tool.search(query, limit=limit)
        elif tool_name == "fetch_web":
            url = kwargs.get("url", "")
            return await self.search_tool.fetch_web(url)
        else:
            logger.warning("Unknown tool: %s", tool_name)
            return None
