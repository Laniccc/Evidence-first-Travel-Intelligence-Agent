"""Gap-fill planner: allowed_tools intersection and policy-reject retry."""

from __future__ import annotations

from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.official_candidate_bridge import collect_readable_urls_for_claim
from app.schemas.user_query import TravelAgentState
from tools.official_source.url_normalizer import is_readable_page_url


def test_gap_policy_reject_records_failed_tool_and_retries():
    ctx: dict = {"gap_filling": True, "_gap_failed_tools": []}
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="official_page_reader_mcp",
        arguments={},
    )
    exc = ValueError("official_page_reader_mcp requires a readable url")
    recovered = ClaudeStateRunner._recover_policy_reject(
        TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯门票"),
        action,
        exc,
        ctx,
    )
    assert recovered is True
    assert "official_page_reader_mcp" in ctx["_gap_failed_tools"]


def test_collect_readable_urls_excludes_lbsyun():
    state = TravelAgentState(session_id="s", query_id="q2", raw_user_query="喀纳斯门票")
    state.structured_result = {
        "keyword_search_results": [
            {"url": "https://lbsyun.baidu.com/index.php?title=open/poitags", "title": "poi tags"}
        ]
    }
    urls = collect_readable_urls_for_claim(state, "ticket_price")
    assert not any("lbsyun" in u for u in urls)
    assert not is_readable_page_url("https://lbsyun.baidu.com/faq/api?title=webapi/guide/webservice-placeapi")
