"""Helpers for retrieval ledger tests."""

from __future__ import annotations

from app.orchestrator.retrieval_attempt_ledger import get_ledger, save_ledger
from app.schemas.tool_trace import ToolTrace
from app.schemas.user_query import TravelAgentState


def mark_ticket_families_attempted(state: TravelAgentState) -> None:
    ledger = get_ledger(state, "ticket_price")
    for family in ("geo_resolution", "search", "map_candidate", "ticket_platform"):
        ledger.record_family(family, evidence_count=1)
    ledger.record_skip("official_source", "test skip")
    save_ledger(state, ledger)
    state.structured_result = {
        **(state.structured_result or {}),
        "subagent_results": [
            {"subagent": "fact_search_agent", "evidence_count": 2, "search_query": "喀纳斯湖 游船 船票"},
        ],
    }
    state.tool_traces = [
        *(state.tool_traces or []),
        ToolTrace(tool_name="fliggy_ticket_api_mcp"),
        ToolTrace(tool_name="baidu_place_detail_mcp"),
    ]


def mark_opening_hours_families_attempted(state: TravelAgentState) -> None:
    ledger = get_ledger(state, "opening_hours")
    for family in ("geo_resolution", "search", "map_candidate"):
        ledger.record_family(family, evidence_count=1)
    ledger.record_skip("official_source", "no_urls_or_search_results")
    ledger.record_skip("official_page_reader", "no_official_candidate_url")
    save_ledger(state, ledger)
    state.tool_traces = [
        *(state.tool_traces or []),
        ToolTrace(tool_name="search_mcp"),
        ToolTrace(tool_name="baidu_place_search_mcp"),
    ]
