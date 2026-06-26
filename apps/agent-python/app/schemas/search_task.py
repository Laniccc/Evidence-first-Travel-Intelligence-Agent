"""Evidence lookup tasks delegated from S5 orchestrator to functional sub-agents."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator


def normalize_tool_parameters(raw: dict[str, Any] | None) -> dict[str, str]:
    """Coerce orchestrator/LLM tool_parameters into str values for MCP adapters."""
    if not raw or not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if isinstance(value, list):
            parts = [str(item).strip() for item in value if str(item).strip()]
            if parts:
                out[str(key)] = " | ".join(parts)
            continue
        if isinstance(value, dict):
            out[str(key)] = json.dumps(value, ensure_ascii=False)
            continue
        text = str(value).strip()
        if text:
            out[str(key)] = text
    return out


class SearchTask(BaseModel):
    """One delegated evidence lookup executed by an S5 functional sub-agent."""

    task_id: str
    target_subagent: str = Field(
        default="",
        description="entity_resolution_agent | route_feasibility_agent | fact_search_agent | ...",
    )
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

    @field_validator("tool_parameters", mode="before")
    @classmethod
    def _coerce_tool_parameters(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return normalize_tool_parameters(value)
        return {}
