"""Deterministic official-first pipeline for strict_fact_lookup."""

from __future__ import annotations

import logging

from app.agents.delegated_mcp_runner import run_delegated_mcp
from app.config import get_settings
from app.orchestrator.fact_lookup_anchor_policy import is_geographic_fact_need, resolved_place_label
from app.orchestrator.fact_lookup_policy import (
    count_actionable_fact_claims,
    has_authoritative_geo_evidence,
    has_official_fact_evidence,
    pipeline_search_queries,
    primary_fact_need_from_state,
)
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState

logger = logging.getLogger(__name__)


def _ticket_crawler_enabled() -> bool:
    s = get_settings()
    return bool(s.enable_ticket_platform_crawlers or s.enable_review_crawler_providers)


def _pipeline_satisfied(merged_evidence: list, need: str) -> bool:
    if count_actionable_fact_claims(merged_evidence, need) < 1:
        return False
    if is_geographic_fact_need(need):
        return has_authoritative_geo_evidence(merged_evidence, need) or count_actionable_fact_claims(
            merged_evidence, need
        ) >= 2
    return has_official_fact_evidence(merged_evidence, need) or count_actionable_fact_claims(
        merged_evidence, need
    ) >= 2


def _build_pipeline_steps(state: TravelAgentState, need: str, place: str, search_queries: list[str]) -> list[tuple[str, dict]]:
    steps: list[tuple[str, dict]] = []

    if is_geographic_fact_need(need):
        for tool in ("wikidata_mcp", "wikipedia_mcp", "osm_mcp"):
            steps.append(
                (
                    tool,
                    {
                        "query": search_queries[0],
                        "lookup_intent": f"地理权威源核实{place}海拔",
                    },
                )
            )
        for q in search_queries:
            steps.append(
                (
                    "search_mcp",
                    {
                        "query": q,
                        "lookup_intent": f"检索{place}海拔线索",
                    },
                )
            )
    else:
        steps.append(
            (
                "search_mcp",
                {
                    "query": search_queries[0],
                    "lookup_intent": f"检索{need}官方线索",
                },
            )
        )

    steps.extend(
        [
            (
                "official_source_discovery_mcp",
                {
                    "query": search_queries[0],
                    "lookup_intent": f"识别{place}官方来源",
                },
            ),
            (
                "official_page_reader_mcp",
                {
                    "query": search_queries[0],
                    "lookup_intent": f"读取官方页提取{need}",
                },
            ),
        ]
    )

    if need == "ticket_price" and _ticket_crawler_enabled():
        for tool in ("ctrip_ticket_signal_crawler_mcp", "dianping_ticket_signal_crawler_mcp"):
            steps.append(
                (
                    tool,
                    {
                        "query": f"{place} 门票",
                        "lookup_intent": f"平台票务信号：{place}",
                    },
                )
            )
    return steps


async def run_fact_lookup_pipeline(
    *,
    tools_registry,
    state: TravelAgentState,
    base_task: SearchTask,
    working_evidence: list,
    prompt_context: dict | None,
    parent_subagent: str = "fact_lookup_agent",
) -> tuple[list, list, int]:
    """Official-first retrieval; elevation uses geo-authority tools before generic web search."""
    need = primary_fact_need_from_state(state)
    whitelist = (prompt_context or {}).get("tool_whitelist")
    all_evidence: list = []
    all_traces: list = []
    tool_call_count = 0

    if _pipeline_satisfied(working_evidence, need):
        return all_evidence, all_traces, tool_call_count

    place = (base_task.tool_parameters or {}).get("place_name") or resolved_place_label(state)
    search_queries = pipeline_search_queries(state, need)
    common_params = {
        **(base_task.tool_parameters or {}),
        "place_name": place,
        "information_need": need,
        "claim_target": need,
        "prior_evidence": working_evidence,
    }

    steps = _build_pipeline_steps(state, need, place, search_queries)
    merged_evidence = list(working_evidence)

    for idx, (tool_name, patch) in enumerate(steps):
        if whitelist is not None and not whitelist.is_allowed(tool_name):
            continue
        if _pipeline_satisfied(merged_evidence, need):
            break
        task = base_task.model_copy(
            update={
                "task_id": f"{base_task.task_id}-fact-{idx}",
                "claim_target": need,
                "information_need": need,
                "search_query": patch.get("query") or search_queries[0],
                "lookup_intent": patch.get("lookup_intent") or search_queries[0],
                "preferred_tool": tool_name,
                "tool_parameters": {
                    **common_params,
                    **{k: v for k, v in patch.items() if k not in {"lookup_intent", "query"}},
                },
            }
        )
        try:
            ev, tr = await run_delegated_mcp(
                tools_registry,
                tool_name,
                task,
                state,
                prompt_context,
                subagent=parent_subagent,
                phase="gap_fill",
            )
            all_evidence.extend(ev)
            all_traces.extend(tr)
            merged_evidence.extend(ev)
            tool_call_count += 1
        except Exception as exc:
            logger.warning("fact_lookup %s failed: %s", tool_name, exc)

    if all_evidence or tool_call_count:
        structured = dict(state.structured_result or {})
        runs = list(structured.get("fact_lookup_pipeline_runs") or [])
        runs.append(
            {
                "information_need": need,
                "tool_call_count": tool_call_count,
                "actionable_claims": count_actionable_fact_claims(merged_evidence, need),
                "has_official": has_official_fact_evidence(merged_evidence, need),
                "has_authoritative_geo": has_authoritative_geo_evidence(merged_evidence, need),
                "search_queries": search_queries[:4],
            }
        )
        structured["fact_lookup_pipeline_runs"] = runs[-8:]
        state.structured_result = structured

    return all_evidence, all_traces, tool_call_count
