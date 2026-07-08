"""Run per-anchor nearby retrieval (Baidu) after anchor strategy."""

from __future__ import annotations

import logging

from app.agents.delegated_mcp_runner import run_delegated_mcp
from app.agents.subagent_delegate import delegate_subagent
from app.orchestrator.mcp_tool_arguments import nearby_coordinate_patch
from app.orchestrator.nearby_recommendation_policy import baidu_tag_for_need, nearby_query_suffix_for_need
from app.orchestrator.nearby_category_registry import taxonomy_meta_for_need
from app.orchestrator.place_disambiguation_guard import extract_place_candidates
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


async def run_nearby_retrieval_after_anchor(
    *,
    tools_registry,
    state: TravelAgentState,
    base_task: SearchTask,
    nearby_claim: str,
    working_evidence: list,
    prompt_context: dict | None,
    parent_subagent: str = "entity_resolution_agent",
) -> tuple[list, list, int]:
    """Delegate anchor strategy, then Baidu nearby search per search target."""
    all_evidence: list = []
    all_traces: list = []
    tool_call_count = 0
    whitelist = (prompt_context or {}).get("tool_whitelist")

    candidates = extract_place_candidates(working_evidence)
    strategy_out = await delegate_subagent(
        "nearby_anchor_strategy_agent",
        state,
        {
            "task_id": f"{base_task.task_id}-anchor-strategy",
            "nearby_claim": nearby_claim,
            "candidates": candidates,
            "evidence_list": working_evidence,
            "parent_subagent": parent_subagent,
        },
        tools_registry=tools_registry,
        prompt_context=prompt_context,
        parent_subagent=parent_subagent,
    )
    targets = strategy_out.get("search_targets") or []
    if not targets:
        return all_evidence, all_traces, tool_call_count

    saved_evidence = state.evidence
    merged = list(saved_evidence) + [ev for ev in working_evidence if ev not in saved_evidence]
    state.evidence = merged

    try:
        for idx, target in enumerate(targets):
            coords = target.get("coordinates")
            if not coords:
                continue
            candidate = target.get("candidate") if isinstance(target.get("candidate"), dict) else {}
            location_key = str(target.get("location_key") or "")
            candidate_name = str(target.get("candidate_name") or candidate.get("name") or "")
            radius = int(target.get("radius") or 3000)
            tag = baidu_tag_for_need(nearby_claim)

            coord_patch = nearby_coordinate_patch(coords, radius=radius)
            base_params = {
                k: v
                for k, v in (base_task.tool_parameters or {}).items()
                if k not in {"query", "tag", "nearby_search", "latitude", "longitude", "radius"}
            }
            query_suffix = nearby_query_suffix_for_need(nearby_claim)
            anchor_label = candidate_name or base_task.search_query or ""
            search_query = f"{anchor_label} {query_suffix}".strip()

            tool_parameters = {
                **base_params,
                **coord_patch,
                **taxonomy_meta_for_need(nearby_claim),
                "query": search_query,
                "anchor_location_key": location_key,
                "anchor_candidate_name": candidate_name,
                "nearby_anchor_label": candidate_name,
            }
            if tag:
                tool_parameters["tag"] = tag
            if coord_patch:
                tool_parameters.pop("region", None)

            nearby_task = base_task.model_copy(
                update={
                    "task_id": f"{base_task.task_id}-nearby-{idx}",
                    "claim_target": nearby_claim,
                    "information_need": nearby_claim,
                    "search_query": search_query,
                    "lookup_intent": target.get("rationale")
                    or f"锚点周边检索：{candidate_name or nearby_claim}",
                    "preferred_tool": "baidu_place_search_mcp",
                    "tool_parameters": tool_parameters,
                }
            )

            if not whitelist or whitelist.is_allowed("baidu_place_search_mcp"):
                try:
                    nb_ev, nb_tr = await run_delegated_mcp(
                        tools_registry,
                        "baidu_place_search_mcp",
                        nearby_task,
                        state,
                        prompt_context,
                        subagent=parent_subagent,
                    )
                    all_evidence.extend(nb_ev)
                    all_traces.extend(nb_tr)
                    tool_call_count += 1
                except Exception as exc:
                    logger.warning("nearby baidu %s failed: %s", candidate_name, exc)
    finally:
        state.evidence = saved_evidence

    structured = dict(state.structured_result or {})
    runs = list(structured.get("nearby_per_candidate_runs") or [])
    runs.append(
        {
            "nearby_claim": nearby_claim,
            "target_count": len(targets),
            "evidence_count": len(all_evidence),
        }
    )
    structured["nearby_per_candidate_runs"] = runs[-12:]
    state.structured_result = structured

    return all_evidence, all_traces, tool_call_count
