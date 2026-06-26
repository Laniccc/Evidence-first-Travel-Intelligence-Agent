"""S5 sub-agent: strict fact lookup (anchor → official-first pipeline)."""

from __future__ import annotations

import logging
import uuid

from app.agents.delegated_mcp_runner import pick_tool_from_priority, run_delegated_mcp
from app.agents.fact_lookup_pipeline_runner import run_fact_lookup_pipeline
from app.agents.s5_subagent_registry import S5_SUBAGENT_PROFILES
from app.orchestrator.fact_lookup_anchor_policy import (
    apply_fact_anchor_from_evidence,
    interpret_place_for_fact_need,
    needs_geo_anchor,
    raw_place_label,
    resolved_place_label,
)
from app.orchestrator.fact_lookup_policy import primary_fact_need_from_state
from app.orchestrator.place_disambiguation_guard import extract_place_candidates
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)

_PROFILE = S5_SUBAGENT_PROFILES["fact_lookup_agent"]
_ER_PROFILE = S5_SUBAGENT_PROFILES["entity_resolution_agent"]


class FactLookupAgent:
    """LOOKUP task-class agent: geo anchor + deterministic official-first fact pipeline."""

    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    @staticmethod
    def _task_from_arguments(arguments: dict, state: TravelAgentState) -> SearchTask:
        need = arguments.get("information_need") or arguments.get("claim_target") or primary_fact_need_from_state(state)
        place = resolved_place_label(state) or arguments.get("search_query") or state.raw_user_query[:64]
        place = interpret_place_for_fact_need(place, need)
        frame = state.semantic_frame
        raw = {
            "task_id": arguments.get("task_id") or f"fact-{uuid.uuid4().hex[:8]}",
            "lookup_intent": arguments.get("lookup_intent") or f"核实{need}硬事实",
            "claim_target": need,
            "information_need": need,
            "search_query": arguments.get("search_query") or place,
            "anchor_keywords": arguments.get("anchor_keywords") or [place[:32]],
            "preferred_tool": arguments.get("preferred_tool") or "search_mcp",
            "tool_parameters": arguments.get("tool_parameters") or {},
            "rationale": arguments.get("rationale") or "",
        }
        if frame and frame.entities:
            raw["tool_parameters"] = {
                **raw["tool_parameters"],
                "city": frame.entities.city or raw["tool_parameters"].get("city"),
                "region": frame.entities.region or raw["tool_parameters"].get("region"),
                "country": frame.entities.country or raw["tool_parameters"].get("country") or "China",
                "place_name": place,
            }
        return SearchTask.model_validate(raw)

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        if not self.tools:
            raise RuntimeError("Tool registry unavailable for fact_lookup_agent")

        prompt_context = prompt_context or {}
        need = arguments.get("information_need") or arguments.get("claim_target") or primary_fact_need_from_state(state)
        task = self._task_from_arguments(arguments, state)
        whitelist = prompt_context.get("tool_whitelist")
        all_evidence: list = []
        all_traces: list = []
        tool_call_count = 0
        working_evidence = list(state.evidence or [])

        anchor_query = raw_place_label(state) or task.search_query
        if needs_geo_anchor(state) or not extract_place_candidates(working_evidence):
            tool_name = pick_tool_from_priority(
                _ER_PROFILE.tool_priority,
                whitelist,
                preferred="baidu_place_search_mcp",
                state=state,
                claim_type="entity_resolution",
                subagent="fact_lookup_agent",
            )
            if tool_name:
                anchor_task = task.model_copy(
                    update={
                        "task_id": f"{task.task_id}-anchor",
                        "claim_target": "entity_resolution",
                        "information_need": "entity_resolution",
                        "search_query": anchor_query,
                        "lookup_intent": f"锚定景区/山体：{anchor_query}",
                    }
                )
                try:
                    ev, tr = await run_delegated_mcp(
                        self.tools,
                        tool_name,
                        anchor_task,
                        state,
                        prompt_context,
                        subagent="fact_lookup_agent",
                    )
                    all_evidence.extend(ev)
                    all_traces.extend(tr)
                    working_evidence.extend(ev)
                    tool_call_count += 1
                    apply_fact_anchor_from_evidence(state, need)
                    task = self._task_from_arguments(arguments, state)
                except Exception as exc:
                    logger.warning("fact_lookup anchor failed: %s", exc)

        pipe_ev, pipe_tr, pipe_calls = await run_fact_lookup_pipeline(
            tools_registry=self.tools,
            state=state,
            base_task=task,
            working_evidence=working_evidence + all_evidence,
            prompt_context=prompt_context,
            parent_subagent="fact_lookup_agent",
        )
        all_evidence.extend(pipe_ev)
        all_traces.extend(pipe_tr)
        tool_call_count += pipe_calls

        structured = dict(state.structured_result or {})
        anchor = structured.get("fact_anchor")

        return {
            "subagent": "fact_lookup_agent",
            "task_id": task.task_id,
            "lookup_intent": task.lookup_intent,
            "claim_target": task.claim_target,
            "information_need": task.information_need,
            "search_query": task.search_query,
            "fact_anchor": anchor,
            "place_candidates": extract_place_candidates(working_evidence + all_evidence),
            "evidence": all_evidence,
            "tool_traces": all_traces,
            "tool_call_count": tool_call_count,
        }
