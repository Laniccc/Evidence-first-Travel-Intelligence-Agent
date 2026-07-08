"""S5 sub-agent: short-term weather / climate MCP."""

from __future__ import annotations

import uuid

from app.agents.delegated_mcp_runner import pick_tool_from_priority, run_delegated_mcp
from app.agents.s5_subagent_registry import S5_SUBAGENT_PROFILES
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

_PROFILE = S5_SUBAGENT_PROFILES["weather_context_agent"]


class WeatherContextAgent:
    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        if not self.tools:
            raise RuntimeError("Tool registry unavailable for weather_context_agent")

        frame = state.semantic_frame
        place = (
            arguments.get("place_name")
            or (frame.entities.places[0] if frame and frame.entities and frame.entities.places else None)
            or (frame.entities.city if frame and frame.entities else None)
        )
        task = SearchTask(
            task_id=arguments.get("task_id") or f"weather-{uuid.uuid4().hex[:8]}",
            lookup_intent=arguments.get("lookup_intent") or "获取目的地短期天气",
            claim_target=arguments.get("claim_target") or "forecast",
            anchor_keywords=arguments.get("anchor_keywords") or ([str(place)] if place else []),
            search_query=arguments.get("search_query") or str(place or state.raw_user_query)[:96],
            information_need=arguments.get("information_need") or "forecast",
            preferred_tool=arguments.get("preferred_tool") or "baidu_weather_mcp",
            tool_parameters=arguments.get("tool_parameters") or {},
        )
        whitelist = (prompt_context or {}).get("tool_whitelist")
        tool_name = pick_tool_from_priority(
            _PROFILE.tool_priority,
            whitelist,
            preferred=task.preferred_tool,
            state=state,
            claim_type=task.claim_target or task.information_need,
            subagent="weather_context_agent",
        )
        if not tool_name:
            raise ValueError("No allowed MCP tool for weather_context_agent")

        evidence, traces = await run_delegated_mcp(
            self.tools,
            tool_name,
            task,
            state,
            prompt_context,
            subagent="weather_context_agent",
        )
        return {
            "subagent": "weather_context_agent",
            "task_id": task.task_id,
            "lookup_intent": task.lookup_intent,
            "claim_target": task.claim_target,
            "search_query": task.search_query,
            "selected_tool": tool_name,
            "evidence": evidence,
            "tool_traces": traces,
            "tool_call_count": 1,
        }
