"""Phase-scoped fact lookup execution — one source_family per invocation."""

from __future__ import annotations

import logging
from typing import Any

from app.agents.delegated_mcp_runner import run_delegated_mcp
from app.orchestrator.fact_lookup_anchor_policy import resolved_place_label
from app.orchestrator.fact_lookup_policy import primary_fact_need_from_state
from app.orchestrator.lookup_query_objectives import (
    build_lookup_query_objectives,
    build_peak_elevation_objectives,
    objective_to_search_query,
)
from app.orchestrator.lookup_research_chain import (
    build_retrieval_audit,
    mark_phase_complete,
    merge_chain_updates,
)
from app.orchestrator.s5_tool_attempt_ledger import get_ledger
from app.orchestrator.ticket_lookup_helpers import has_ticket_url_inputs
from app.schemas.lookup_research_chain import LookupPhase, SourceFamily
from app.schemas.search_task import SearchTask
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name

logger = logging.getLogger(__name__)

_SOURCE_FAMILY_TOOLS: dict[SourceFamily, list[str]] = {
    "official_operator": [
        "official_source_discovery_mcp",
        "search_mcp",
        "official_page_reader_mcp",
        "browser_mcp",
    ],
    "government_tourism": [
        "search_mcp",
        "official_page_reader_mcp",
        "official_source_discovery_mcp",
    ],
    "ticket_platform": [
        "fliggy_ticket_api_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "baidu_place_detail_mcp",
        "search_mcp",
    ],
    "map_candidate": ["baidu_place_detail_mcp", "search_mcp"],
    "geo_authority": ["wikidata_mcp", "wikipedia_mcp", "osm_mcp", "search_mcp"],
    "web_reference": ["search_mcp"],
}


def _has_url_inputs(state: TravelAgentState) -> bool:
    if has_ticket_url_inputs(state):
        return True
    for ev in state.evidence or []:
        url = getattr(ev, "source_url", None)
        if url and str(url).startswith("http"):
            return True
    structured = state.structured_result or {}
    for row in structured.get("keyword_search_results") or []:
        if row.get("selected_tool") in {"search_mcp", "browser_mcp"}:
            return True
    return False


_OFFICIAL_DISCOVERY_TOOLS = frozenset(
    {"official_source_discovery_mcp", "official_page_reader_mcp"}
)


async def run_lookup_phase(
    *,
    tools_registry,
    state: TravelAgentState,
    lookup_phase: LookupPhase,
    source_family: SourceFamily,
    claim_target: str | None = None,
    query_objectives: list[dict] | None = None,
    chain_updates: dict | None = None,
    prompt_context: dict | None = None,
    task_id: str = "lookup-phase",
) -> dict[str, Any]:
    need = claim_target or primary_fact_need_from_state(state)
    merge_chain_updates(state, chain_updates)

    from app.schemas.lookup_research_chain import LookupQueryObjective

    if query_objectives:
        objectives = [LookupQueryObjective.model_validate(o) for o in query_objectives]
    elif lookup_phase == "peak_elevation_lookup":
        from app.orchestrator.peak_elevation_extraction import discover_peak_names_from_evidence

        peak_names = discover_peak_names_from_evidence(list(state.evidence or []))
        objectives = build_peak_elevation_objectives(
            state, place=resolved_place_label(state), peak_names=peak_names
        )
        source_family = "geo_authority"
        tools = _SOURCE_FAMILY_TOOLS.get("geo_authority", ["search_mcp"])
    elif lookup_phase == "official_ticket_page_discovery":
        objectives = build_lookup_query_objectives(state, need, "official_operator")
        source_family = "official_operator"
        tools = ["official_page_reader_mcp", "browser_mcp", "search_mcp"]
    elif lookup_phase == "platform_ticket_candidate":
        objectives = build_lookup_query_objectives(state, need, "ticket_platform")
        source_family = "ticket_platform"
        tools = _SOURCE_FAMILY_TOOLS.get("ticket_platform", ["fliggy_ticket_api_mcp"])
    elif lookup_phase == "ticket_price_extraction":
        objectives = build_lookup_query_objectives(state, need, "ticket_platform")
        source_family = "ticket_platform"
        tools = ["search_mcp", "browser_mcp", "official_page_reader_mcp", *(_SOURCE_FAMILY_TOOLS.get("ticket_platform") or [])]
    elif lookup_phase == "official_site_discovery":
        objectives = build_lookup_query_objectives(state, need, "official_operator")
        source_family = "official_operator"
        tools = _SOURCE_FAMILY_TOOLS.get("official_operator", ["search_mcp"])
    else:
        objectives = build_lookup_query_objectives(state, need, source_family)

    evidence: list = []
    tool_traces: list = []
    tools = _SOURCE_FAMILY_TOOLS.get(source_family, ["search_mcp"])
    max_calls = 4 if lookup_phase in {"peak_elevation_lookup", "platform_ticket_candidate"} else (
        3 if source_family == "geo_authority" else 2
    )
    whitelist = (prompt_context or {}).get("tool_whitelist")
    place = resolved_place_label(state)
    ledger = get_ledger(state)
    tried = ledger.attempted_tools(subagent="fact_lookup_agent", claim_type=need)

    for idx, obj in enumerate(objectives[:max_calls]):
        query = (obj.search_query or "").strip() or objective_to_search_query(obj)
        tool = None
        for candidate in tools:
            resolved = resolve_tool_name(candidate)
            if whitelist is not None and not whitelist.is_allowed(resolved):
                continue
            if resolved not in tried:
                tool = candidate
                break
        if not tool:
            continue
        if resolve_tool_name(tool) in _OFFICIAL_DISCOVERY_TOOLS and not _has_url_inputs(state):
            continue
        tried.add(resolve_tool_name(tool))
        task = SearchTask(
            task_id=f"{task_id}-{idx}",
            search_query=query,
            lookup_intent=obj.query_intent or query,
            claim_target=need,
            information_need=need,
            preferred_tool=tool,
            tool_parameters={
                "place_name": place,
                "information_need": need,
                "claim_target": need,
                "source_family": source_family,
                "lookup_phase": lookup_phase,
            },
        )
        try:
            ev, tr = await run_delegated_mcp(
                tools_registry,
                tool,
                task,
                state,
                prompt_context,
                subagent="fact_lookup_agent",
            )
            evidence.extend(ev)
            tool_traces.extend(tr)
        except Exception as exc:
            logger.warning("lookup phase %s/%s tool %s failed: %s", lookup_phase, source_family, tool, exc)

    if lookup_phase in (
        "official_discovery",
        "official_site_discovery",
        "official_ticket_page_discovery",
        "platform_ticket_candidate",
        "ticket_price_extraction",
        "fact_acquisition",
        "peak_elevation_lookup",
    ):
        mark_phase_complete(state, lookup_phase)
    from app.orchestrator.peak_elevation_extraction import extract_peak_elevation_table

    table = extract_peak_elevation_table(list(state.evidence or []) + list(evidence), place_name=place)
    if table.peaks or table.value_granularity != "none":
        structured = dict(state.structured_result or {})
        structured["peak_elevation_table"] = table.model_dump()
        state.structured_result = structured
    build_retrieval_audit(state)

    return {
        "subagent": "fact_lookup_agent",
        "lookup_phase": lookup_phase,
        "source_family": source_family,
        "claim_target": need,
        "search_query": objectives[0].anchor_terms[0] if objectives and objectives[0].anchor_terms else place,
        "query_objectives": [o.model_dump() for o in objectives],
        "evidence": evidence,
        "tool_traces": tool_traces,
        "evidence_count": len(evidence),
        "lookup_research_chain": (state.structured_result or {}).get("lookup_research_chain"),
    }
