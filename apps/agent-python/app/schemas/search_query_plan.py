"""Structured search query plan (rewrite → retrieve)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchQueryPlanItem(BaseModel):
    """One claim-targeted search angle — not a synonym repeat of other items."""

    anchor_entity: str
    claim_type: str
    search_goal: str
    search_query: str
    information_need: str
    preferred_tool: str = "search_mcp"
    source_hint: str = ""
    time_hint: str = ""
    expected_source_types: list[str] = Field(default_factory=list)
    anchor_keywords: list[str] = Field(default_factory=list)
    tool_parameters: dict[str, str] = Field(default_factory=dict)
