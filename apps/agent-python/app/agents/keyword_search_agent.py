"""S5 sub-agent: execute one evidence lookup via allowed MCP tools (first-party CALL_TOOL)."""

from __future__ import annotations

import logging
import re

from app.orchestrator.agent_tool_catalog import catalog_entry
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.comparison_helpers import (
    active_place_name,
    build_comparison_search_query,
    comparison_search_anchors,
    is_comparison_mode,
)
from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments
from app.schemas.search_task import SearchTask
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.mcp.tool_specs import NEED_TOOL_PROFILES
from app.tools.tool_name_resolver import resolve_tool_name

logger = logging.getLogger(__name__)

_MIN_ANCHOR_LEN = 2
_ROUTE_TOOLS = frozenset({"baidu_route_mcp", "baidu_route_matrix_mcp"})
_ROUTE_NEEDS = frozenset(
    {
        "route_plan",
        "transport_planning",
        "distance",
        "duration",
        "itinerary_feasibility",
        "transit",
    }
)


class KeywordSearchAgent:
    """Run one delegated lookup task; pick MCP from catalog + whitelist; invoke tool."""

    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    @staticmethod
    def _is_route_task(task: SearchTask) -> bool:
        params = task.tool_parameters or {}
        if params.get("origin") and params.get("destination"):
            return True
        preferred = resolve_tool_name(task.preferred_tool or "")
        return preferred in _ROUTE_TOOLS

    @staticmethod
    def validate_task(task: SearchTask) -> None:
        if not task.lookup_intent.strip() and not task.search_query.strip():
            raise ValueError("lookup_intent or search_query must not be empty")
        if KeywordSearchAgent._is_route_task(task):
            params = task.tool_parameters or {}
            if not (params.get("origin") and params.get("destination")):
                raise ValueError(
                    "route lookup requires tool_parameters.origin and tool_parameters.destination"
                )
            return
        if not task.anchor_keywords:
            raise ValueError("anchor_keywords must not be empty for web-search lookups")
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

    @staticmethod
    def pick_tool(
        task: SearchTask,
        whitelist: ToolWhitelist | None,
        agent_tool_definitions: list[dict] | None = None,
    ) -> str:
        """Select MCP using task delegation, tool catalog, and NEED_TOOL_PROFILES."""
        params = task.tool_parameters or {}
        need = (task.claim_target or task.information_need or "").strip()

        if params.get("origin") and params.get("destination"):
            for route_tool in ("baidu_route_mcp", "baidu_route_matrix_mcp"):
                resolved = resolve_tool_name(route_tool)
                if whitelist is None or whitelist.is_allowed(resolved):
                    return resolved

        preferred = resolve_tool_name(task.preferred_tool or "search_mcp")
        if preferred != "search_mcp" and (whitelist is None or whitelist.is_allowed(preferred)):
            return preferred

        if agent_tool_definitions and need:
            ranked: list[str] = []
            for defn in agent_tool_definitions:
                name = resolve_tool_name(str(defn.get("name") or ""))
                if not name or name.endswith("_agent"):
                    continue
                satisfies = set(defn.get("satisfies_needs") or [])
                if need not in satisfies:
                    continue
                if whitelist is not None and not whitelist.is_allowed(name):
                    continue
                ranked.append(name)
            if ranked:
                return ranked[0]

        if need in _ROUTE_NEEDS:
            for route_tool in ("baidu_place_search_mcp", "baidu_route_mcp"):
                resolved = resolve_tool_name(route_tool)
                if whitelist is None or whitelist.is_allowed(resolved):
                    return resolved

        for tool in NEED_TOOL_PROFILES.get(need, []):
            resolved = resolve_tool_name(tool)
            if whitelist is None or whitelist.is_allowed(resolved):
                return resolved

        spec = catalog_entry(preferred)
        if spec and need in (spec.satisfies_needs or []):
            if whitelist is None or whitelist.is_allowed(preferred):
                return preferred

        for fallback in (
            "search_mcp",
            "official_page_reader_mcp",
            "ctrip_ticket_signal_crawler_mcp",
            "dianping_ticket_signal_crawler_mcp",
            "baidu_place_search_mcp",
        ):
            if whitelist is None or whitelist.is_allowed(fallback):
                return fallback

        allowed = whitelist.allowed_tool_names() if whitelist else []
        if allowed:
            return allowed[0]
        return preferred

    @staticmethod
    def build_tool_payload(
        tool_name: str,
        task: SearchTask,
        state: TravelAgentState,
        prompt_context: dict | None,
    ) -> dict:
        args = dict(task.tool_parameters or {})
        if task.search_query.strip():
            args.setdefault("query", task.search_query.strip())
        elif task.lookup_intent.strip():
            args.setdefault("query", task.lookup_intent.strip()[:200])
        if task.information_need:
            args.setdefault("information_need", task.information_need)
        if task.claim_target:
            args.setdefault("claim_target", task.claim_target)
        if task.lookup_intent:
            args.setdefault("lookup_intent", task.lookup_intent)
        return enrich_mcp_tool_arguments(
            tool_name,
            args,
            state=state,
            prompt_context=prompt_context,
        )

    @staticmethod
    def _query_contains_anchor(query: str, anchors: list[str]) -> bool:
        for anchor in anchors:
            token = str(anchor).strip()
            if len(token) < 2:
                continue
            if token in query:
                return True
        return False

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        if not self.tools:
            raise RuntimeError("Tool registry unavailable for keyword_search_agent")

        prompt_context = prompt_context or {}
        tool_defs = (
            prompt_context.get("agent_tool_definitions")
            or (state.structured_result or {}).get("_agent_tool_definitions")
            or []
        )

        raw = {
            "task_id": arguments.get("task_id") or arguments.get("id") or "keyword-search",
            "lookup_intent": arguments.get("lookup_intent") or arguments.get("rationale") or "",
            "claim_target": arguments.get("claim_target") or "",
            "anchor_keywords": arguments.get("anchor_keywords") or [],
            "search_query": arguments.get("search_query") or arguments.get("query") or "",
            "information_need": arguments.get("information_need")
            or ClaimSearchPlanner.primary_information_need(state)
            or "unknown",
            "preferred_tool": arguments.get("preferred_tool") or "search_mcp",
            "tool_parameters": arguments.get("tool_parameters") or {},
            "rationale": arguments.get("rationale") or "",
        }
        if not raw["lookup_intent"] and raw["search_query"]:
            raw["lookup_intent"] = raw["search_query"]
        if not raw["search_query"] and raw["lookup_intent"]:
            raw["search_query"] = raw["lookup_intent"][:96]
        if not raw["claim_target"]:
            raw["claim_target"] = raw["information_need"]

        task = SearchTask.model_validate(raw)
        self.validate_task(task)

        whitelist = prompt_context.get("tool_whitelist")
        tool_name = self.pick_tool(task, whitelist, tool_defs)
        if whitelist is not None and not whitelist.is_allowed(tool_name):
            raise ValueError(f"Tool {tool_name!r} not allowed for keyword_search_agent")

        frame = state.semantic_frame
        current_place = (prompt_context.get("place_name") or active_place_name(state))
        if (
            is_comparison_mode(state)
            and current_place
            and frame
            and not self._is_route_task(task)
        ):
            peers = list(state.comparison_peer_places or [])
            if frame.entities and frame.entities.places:
                peers = peers or [p for p in frame.entities.places if p != current_place]
            if not self._query_contains_anchor(task.search_query, task.anchor_keywords):
                task = task.model_copy(
                    update={
                        "search_query": build_comparison_search_query(
                            current_place,
                            task.information_need or "crowd_level",
                            frame,
                            peer_places=peers,
                            user_query=state.raw_user_query,
                        ),
                        "anchor_keywords": comparison_search_anchors(
                            current_place, frame, peer_places=peers
                        ),
                    }
                )
                self.validate_task(task)

        payload = self.build_tool_payload(tool_name, task, state, prompt_context)

        trace_before = len(self.tools.traces)
        evidence = await self.tools.run_tool(tool_name, **payload)
        new_traces = self.tools.traces[trace_before:]

        return {
            "task_id": task.task_id,
            "lookup_intent": task.lookup_intent,
            "claim_target": task.claim_target,
            "anchor_keywords": task.anchor_keywords,
            "search_query": task.search_query,
            "search_purpose": task.information_need,
            "preferred_tool": task.preferred_tool,
            "tool_parameters": task.tool_parameters,
            "selected_tool": tool_name,
            "information_need": task.information_need,
            "rationale": task.rationale,
            "evidence": evidence,
            "tool_traces": [t.model_dump() for t in new_traces],
            "tool_call_count": 1,
        }
