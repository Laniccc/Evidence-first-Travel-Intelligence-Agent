"""S5 sub-agent: route distance/duration/traffic via Baidu route MCP."""

from __future__ import annotations

import uuid

from app.agents.delegated_mcp_runner import pick_tool_from_priority, run_delegated_mcp
from app.agents.s5_subagent_registry import S5_SUBAGENT_PROFILES
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

_PROFILE = S5_SUBAGENT_PROFILES["route_feasibility_agent"]
_ROUTE_TOOLS = frozenset(
    {"baidu_route_mcp", "baidu_route_matrix_mcp", "baidu_traffic_mcp", "baidu_place_search_mcp"}
)


class RouteFeasibilityAgent:
    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    @staticmethod
    def _task_from_arguments(arguments: dict, state: TravelAgentState) -> SearchTask:
        params = dict(arguments.get("tool_parameters") or {})
        frame = state.semantic_frame
        try:
            from app.orchestrator.mcp_tool_arguments import _route_endpoints_from_text

            parsed_origin, parsed_dest = _route_endpoints_from_text(state.raw_user_query)
        except Exception:
            parsed_origin, parsed_dest = None, None
        if parsed_origin:
            params.setdefault("origin", parsed_origin)
        if parsed_dest:
            params.setdefault("destination", parsed_dest)
        dest = (
            params.get("destination")
            or arguments.get("place_name")
            or (frame.entities.places[0] if frame and frame.entities and frame.entities.places else None)
        )
        if dest:
            params.setdefault("destination", str(dest))
            params.setdefault("place_name", str(dest))
        if not params.get("origin") and state.user_goal and state.user_goal.start_location:
            params.setdefault("origin", state.user_goal.start_location)
        raw = {
            "task_id": arguments.get("task_id") or f"route-{uuid.uuid4().hex[:8]}",
            "lookup_intent": arguments.get("lookup_intent") or "获取城际/景区路线距离与时长",
            "claim_target": arguments.get("claim_target") or "route_plan",
            "anchor_keywords": arguments.get("anchor_keywords") or [],
            "search_query": arguments.get("search_query") or arguments.get("query") or "",
            "information_need": arguments.get("information_need") or "route_plan",
            "preferred_tool": arguments.get("preferred_tool") or "baidu_route_mcp",
            "tool_parameters": params,
            "rationale": arguments.get("rationale") or "",
        }
        if not raw["anchor_keywords"]:
            for token in (params.get("origin"), params.get("destination"), dest):
                if token and str(token).strip():
                    raw["anchor_keywords"].append(str(token).strip())
        if not raw["search_query"]:
            o, d = params.get("origin"), params.get("destination")
            raw["search_query"] = f"{o or ''} {d or ''}".strip() or state.raw_user_query[:96]
        return SearchTask.model_validate(raw)

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        if not self.tools:
            raise RuntimeError("Tool registry unavailable for route_feasibility_agent")

        prompt_context = prompt_context or {}
        task = self._task_from_arguments(arguments, state)
        whitelist = prompt_context.get("tool_whitelist")
        params = task.tool_parameters or {}

        preferred = task.preferred_tool or "baidu_route_mcp"
        if params.get("road_name") or params.get("road"):
            preferred = "baidu_traffic_mcp"
        elif params.get("origins") or params.get("destinations"):
            preferred = "baidu_route_matrix_mcp"
        elif not (params.get("origin") and params.get("destination")):
            preferred = "baidu_place_search_mcp"

        tool_name = pick_tool_from_priority(
            _PROFILE.tool_priority,
            whitelist,
            preferred=preferred,
            state=state,
            claim_type=task.claim_target or task.information_need,
            subagent="route_feasibility_agent",
        )
        if not tool_name:
            raise ValueError("No allowed MCP tool for route_feasibility_agent")

        all_evidence: list = []
        all_traces: list = []
        tool_call_count = 0

        if tool_name == "baidu_route_mcp" and whitelist and whitelist.is_allowed("baidu_place_search_mcp"):
            place = params.get("destination") or params.get("place_name")
            if place and not any(
                getattr(ev, "place_name", None) == place for ev in state.evidence
            ):
                pre = task.model_copy(
                    update={
                        "task_id": f"{task.task_id}-poi",
                        "preferred_tool": "baidu_place_search_mcp",
                        "search_query": str(place),
                    }
                )
                pre_ev, pre_tr = await run_delegated_mcp(
                    self.tools,
                    "baidu_place_search_mcp",
                    pre,
                    state,
                    prompt_context,
                    subagent="route_feasibility_agent",
                )
                all_evidence.extend(pre_ev)
                all_traces.extend(pre_tr)
                tool_call_count += 1

        evidence, traces = await run_delegated_mcp(
            self.tools,
            tool_name,
            task,
            state,
            prompt_context,
            subagent="route_feasibility_agent",
        )
        all_evidence.extend(evidence)
        all_traces.extend(traces)
        tool_call_count += 1

        return {
            "subagent": "route_feasibility_agent",
            "task_id": task.task_id,
            "lookup_intent": task.lookup_intent,
            "claim_target": task.claim_target or ClaimSearchPlanner.primary_information_need(state),
            "anchor_keywords": task.anchor_keywords,
            "search_query": task.search_query,
            "information_need": task.information_need,
            "selected_tool": tool_name,
            "evidence": all_evidence,
            "tool_traces": all_traces,
            "tool_call_count": tool_call_count,
        }
