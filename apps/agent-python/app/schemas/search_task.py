"""Keyword-focused search tasks for S5 controlled A2A."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchTask(BaseModel):
    """One delegated keyword search for a keyword_search_agent."""

    task_id: str
    anchor_keywords: list[str] = Field(
        description="Strict keywords that MUST be reflected in search_query (place, claim, region).",
        min_length=1,
    )
    search_query: str = Field(description="Expanded search string sent to MCP (may add synonyms).")
    information_need: str = "unknown"
    preferred_tool: str = "search_mcp"
    rationale: str = ""
