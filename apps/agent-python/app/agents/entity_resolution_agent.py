"""S5 sub-agent: place/POI entity resolution via Baidu geo MCP (incl. disambiguation branches)."""

from __future__ import annotations

import logging
import uuid

from app.agents.delegated_mcp_runner import pick_tool_from_priority, run_delegated_mcp
from app.agents.nearby_enrichment_runner import run_nearby_enrichment_after_retrieval
from app.agents.nearby_retrieval_runner import run_nearby_retrieval_after_anchor
from app.agents.s5_subagent_registry import S5_SUBAGENT_PROFILES
from app.orchestrator.information_need_aliases import nearby_claims_for_retrieval
from app.orchestrator.place_disambiguation_guard import (
    apply_unique_candidate,
    candidate_baidu_region,
    clear_disambiguation_pending,
    detect_ambiguous_candidates,
    extract_place_candidates,
    mark_disambiguation_pending,
    try_resolve_disambiguation,
)
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState
from tools.mcp.adapters.baidu_response_parser import (
    candidates_are_ambiguous as parser_ambiguous,
)

logger = logging.getLogger(__name__)

_PROFILE = S5_SUBAGENT_PROFILES["entity_resolution_agent"]


class EntityResolutionAgent:
    """Resolve place entities; run region-scoped branch searches when ambiguous."""

    def __init__(self, tools_registry=None) -> None:
        self.tools = tools_registry

    @staticmethod
    def _task_from_arguments(arguments: dict, state: TravelAgentState) -> SearchTask:
        raw = {
            "task_id": arguments.get("task_id") or f"entity-{uuid.uuid4().hex[:8]}",
            "lookup_intent": arguments.get("lookup_intent") or "锚定用户所指地点与行政区",
            "claim_target": arguments.get("claim_target") or "entity_resolution",
            "anchor_keywords": arguments.get("anchor_keywords") or [],
            "search_query": arguments.get("search_query") or arguments.get("query") or "",
            "information_need": arguments.get("information_need") or "entity_resolution",
            "preferred_tool": arguments.get("preferred_tool") or "baidu_place_search_mcp",
            "tool_parameters": arguments.get("tool_parameters") or {},
            "rationale": arguments.get("rationale") or "",
        }
        frame = state.semantic_frame
        if frame and frame.entities and frame.entities.places and not raw["anchor_keywords"]:
            raw["anchor_keywords"] = list(frame.entities.places[:3])
        if not raw["search_query"]:
            if raw["anchor_keywords"]:
                raw["search_query"] = raw["anchor_keywords"][0]
            elif frame and frame.entities and frame.entities.places:
                raw["search_query"] = frame.entities.places[0]
            else:
                raw["search_query"] = state.raw_user_query[:96]
        if not raw["anchor_keywords"] and raw["search_query"]:
            raw["anchor_keywords"] = [raw["search_query"][:32]]
        return SearchTask.model_validate(raw)

    @staticmethod
    def _all_nearby_claims_after_anchor(state: TravelAgentState) -> list[str]:
        return nearby_claims_for_retrieval(state)

    async def run(
        self,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict | None = None,
    ) -> dict:
        if not self.tools:
            raise RuntimeError("Tool registry unavailable for entity_resolution_agent")

        prompt_context = prompt_context or {}
        task = self._task_from_arguments(arguments, state)
        whitelist = prompt_context.get("tool_whitelist")

        all_evidence: list = []
        all_traces: list = []
        tool_call_count = 0
        resolution_status = "pending"
        working_evidence = list(state.evidence)

        tool_name = pick_tool_from_priority(
            _PROFILE.tool_priority,
            whitelist,
            preferred=task.preferred_tool or "baidu_place_search_mcp",
            state=state,
            claim_type=task.claim_target or task.information_need,
            subagent="entity_resolution_agent",
        )
        if not tool_name:
            raise ValueError("No allowed MCP tool for entity_resolution_agent")

        evidence, traces = await run_delegated_mcp(
            self.tools,
            tool_name,
            task,
            state,
            prompt_context,
            subagent="entity_resolution_agent",
        )
        all_evidence.extend(evidence)
        all_traces.extend(traces)
        tool_call_count += 1
        working_evidence.extend(evidence)

        ambiguous = detect_ambiguous_candidates(working_evidence)
        if ambiguous:
            mark_disambiguation_pending(state, ambiguous)
            resolution_status = "ambiguous"
            for candidate in ambiguous:
                region = candidate_baidu_region(candidate)
                if not region:
                    continue
                branch_task = task.model_copy(
                    update={
                        "task_id": f"{task.task_id}-br-{region[:6]}",
                        "tool_parameters": {
                            **(task.tool_parameters or {}),
                            "region": region,
                            "city": str(candidate.get("city") or ""),
                            "province": str(candidate.get("province") or ""),
                        },
                    }
                )
                if not whitelist or whitelist.is_allowed("baidu_place_search_mcp"):
                    try:
                        br_ev, br_tr = await run_delegated_mcp(
                            self.tools,
                            "baidu_place_search_mcp",
                            branch_task,
                            state,
                            prompt_context,
                            subagent="entity_resolution_agent",
                        )
                        all_evidence.extend(br_ev)
                        all_traces.extend(br_tr)
                        tool_call_count += 1
                        working_evidence.extend(br_ev)
                    except Exception as exc:
                        logger.warning("entity_resolution branch %s failed: %s", region, exc)

        saved_evidence = state.evidence
        state.evidence = working_evidence
        if try_resolve_disambiguation(state):
            clear_disambiguation_pending(state)
            resolution_status = "resolved"
        else:
            candidates = extract_place_candidates(working_evidence)
            if candidates and not parser_ambiguous(candidates):
                apply_unique_candidate(state, candidates[0])
                resolution_status = "resolved"
        state.evidence = saved_evidence

        nearby_claims = self._all_nearby_claims_after_anchor(state)
        for nearby_claim in nearby_claims:
            try:
                nb_ev, nb_tr, nb_calls = await run_nearby_retrieval_after_anchor(
                    tools_registry=self.tools,
                    state=state,
                    base_task=task,
                    nearby_claim=nearby_claim,
                    working_evidence=working_evidence,
                    prompt_context=prompt_context,
                    parent_subagent="entity_resolution_agent",
                )
                all_evidence.extend(nb_ev)
                all_traces.extend(nb_tr)
                tool_call_count += nb_calls
                enrich_ev, enrich_tr, enrich_calls = await run_nearby_enrichment_after_retrieval(
                    tools_registry=self.tools,
                    state=state,
                    base_task=task,
                    nearby_claim=nearby_claim,
                    working_evidence=working_evidence + all_evidence,
                    prompt_context=prompt_context,
                    parent_subagent="entity_resolution_agent",
                )
                all_evidence.extend(enrich_ev)
                all_traces.extend(enrich_tr)
                tool_call_count += enrich_calls
            except Exception as exc:
                logger.warning("entity_resolution nearby %s failed: %s", nearby_claim, exc)

        return {
            "subagent": "entity_resolution_agent",
            "task_id": task.task_id,
            "lookup_intent": task.lookup_intent,
            "claim_target": task.claim_target,
            "anchor_keywords": task.anchor_keywords,
            "search_query": task.search_query,
            "information_need": task.information_need,
            "selected_tool": tool_name,
            "resolution_status": resolution_status,
            "place_candidates": extract_place_candidates(working_evidence),
            "evidence": all_evidence,
            "tool_traces": all_traces,
            "tool_call_count": tool_call_count,
        }
