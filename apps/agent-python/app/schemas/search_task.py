"""Evidence lookup tasks delegated from S5 to keyword_search_agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchTask(BaseModel):
    """One delegated evidence lookup for keyword_search_agent (sub-agent executes MCP)."""

    task_id: str
    lookup_intent: str = Field(
        default="",
        description="S5/planner understanding: what evidence to obtain (not just SEO keywords).",
    )
    claim_target: str = Field(
        default="",
        description="Claim type this lookup should support (e.g. distance, opening_hours).",
    )
    anchor_keywords: list[str] = Field(
        default_factory=list,
        description="Place/claim tokens for disambiguation; required for web search tasks.",
    )
    search_query: str = Field(
        default="",
        description="Concrete query string sent to the selected MCP (search phrase or route context).",
    )
    information_need: str = "unknown"
    preferred_tool: str = "search_mcp"
    tool_parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Structured MCP args (origin, destination, url, mode, ...).",
    )
    rationale: str = ""
