"""S5 sub-agent: execute one keyword-anchored search via allowed MCP tools."""

from __future__ import annotations

import logging
import re

from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name

logger = logging.getLogger(__name__)

_MIN_ANCHOR_LEN = 2


class KeywordSearchAgent:
    """Run a single search task with strict anchor keyword validation."""

    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    @staticmethod
    def validate_task(task: SearchTask) -> None:
        if not task.anchor_keywords:
            raise ValueError("anchor_keywords must not be empty")
        if not task.search_query.strip():
            raise ValueError("search_query must not be empty")
        query = task.search_query.strip()
        matched = False
        for anchor in task.anchor_keywords:
            token = str(anchor).strip()
            if len(token) < _MIN_ANCHOR_LEN:
                continue
            if token in query:
                matched = True
                break
            if re.search(re.escape(token), query, re.I):
                matched = True
                break
        if not matched:
            raise ValueError(
                f"search_query must retain at least one anchor keyword from {task.anchor_keywords!r}"
            )

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        if not self.tools:
            raise RuntimeError("Tool registry unavailable for keyword_search_agent")

        task = SearchTask.model_validate(
            {
                "task_id": arguments.get("task_id") or arguments.get("id") or "keyword-search",
                "anchor_keywords": arguments.get("anchor_keywords") or [],
                "search_query": arguments.get("search_query") or arguments.get("query") or "",
                "information_need": arguments.get("information_need")
                or ClaimSearchPlanner.primary_information_need(state)
                or "unknown",
                "preferred_tool": arguments.get("preferred_tool") or "search_mcp",
                "rationale": arguments.get("rationale") or "",
            }
        )
        self.validate_task(task)

        tool_name = resolve_tool_name(task.preferred_tool)
        whitelist = (prompt_context or {}).get("tool_whitelist")
        if whitelist is not None and not whitelist.is_allowed(tool_name):
            raise ValueError(f"Tool {tool_name!r} not allowed for keyword_search_agent")

        frame = state.semantic_frame
        payload = {
            "query": task.search_query,
            "information_need": task.information_need,
            "country": frame.entities.country if frame else None,
            "city": frame.entities.city if frame else None,
            "place_name": frame.entities.places[0] if frame and frame.entities.places else None,
        }

        trace_before = len(self.tools.traces)
        evidence = await self.tools.run_tool(tool_name, **payload)
        new_traces = self.tools.traces[trace_before:]

        return {
            "task_id": task.task_id,
            "anchor_keywords": task.anchor_keywords,
            "search_query": task.search_query,
            "preferred_tool": tool_name,
            "information_need": task.information_need,
            "evidence": evidence,
            "tool_traces": [t.model_dump() for t in new_traces],
            "tool_call_count": 1,
        }
