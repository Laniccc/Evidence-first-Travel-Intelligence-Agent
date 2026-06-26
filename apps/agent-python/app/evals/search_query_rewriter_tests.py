"""Tests for claim-driven search query rewrite."""

from __future__ import annotations

from app.agents.keyword_search_agent import KeywordSearchAgent
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.search_query_rewriter import SearchQueryRewriter
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
)
from app.schemas.user_query import TravelAgentState


def test_elevation_rewrite_produces_chinese_queries_not_claim_slug():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="峨眉山海拔高度多少？")
    state.semantic_frame = SemanticFrame(
        raw_query="峨眉山海拔高度多少？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", region="四川", city="乐山", places=["峨眉山"]),
        information_needs=["elevation"],
        requires_exact_fact=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    ctx = ClaimSearchPlanner.planning_context(state)
    rewriter = SearchQueryRewriter.from_planning_context(ctx, state)
    queries = [t.search_query for t in rewriter.to_search_tasks(max_tasks=4)]
    assert queries
    assert all("general travel advice" not in q for q in queries)
    assert any("海拔" in q for q in queries)
    assert ctx.get("query_rewrite_slots", {}).get("user_need_phrase")


def test_gap_fill_templates_infer_elevation_from_user_query():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="峨眉山海拔高度多少？")
    state.semantic_frame = SemanticFrame(
        raw_query="峨眉山海拔高度多少？",
        entities=SemanticEntities(country="China", city="乐山", places=["峨眉山"]),
        information_needs=["elevation"],
        requires_exact_fact=True,
    )
    ctx = ClaimSearchPlanner.planning_context(state)
    templates = SearchQueryRewriter.from_planning_context(ctx, state).gap_query_templates(
        "general_travel_advice"
    )
    assert templates
    assert any("海拔" in q for q in templates)
    assert not any("general travel advice" in q for q in templates)


def test_pick_tool_elevation_prefers_search_mcp():
    from app.schemas.search_task import SearchTask
    from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist

    task = SearchTask(
        task_id="e1",
        lookup_intent="查海拔",
        claim_target="elevation",
        information_need="elevation",
        search_query="新疆 白沙湖 海拔",
        anchor_keywords=["白沙湖"],
        preferred_tool="search_mcp",
    )
    wl = ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[
            ToolDescriptor(name="search_mcp", description="web", configured=True),
            ToolDescriptor(name="wikipedia_mcp", description="wiki", configured=True),
        ],
    )
    assert KeywordSearchAgent.pick_tool(task, wl) == "search_mcp"


def test_elevation_rewrite_has_no_jinding_template():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="白沙湖海拔多少？")
    state.semantic_frame = SemanticFrame(
        raw_query="白沙湖海拔多少？",
        entities=SemanticEntities(country="China", region="新疆", places=["白沙湖"]),
        information_needs=["elevation"],
    )
    ctx = ClaimSearchPlanner.planning_context(state)
    rewriter = SearchQueryRewriter.from_planning_context(ctx, state)
    tasks = rewriter.to_search_tasks(max_tasks=6)
    assert tasks
    assert not any("金顶" in t.search_query for t in tasks)
    assert all(t.preferred_tool == "search_mcp" for t in tasks)


def test_ticket_price_multi_query_angles():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="束河古镇要门票吗")
    state.semantic_frame = SemanticFrame(
        raw_query="束河古镇要门票吗",
        entities=SemanticEntities(country="China", region="云南", city="丽江", places=["束河古镇"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    ctx = ClaimSearchPlanner.planning_context(state)
    items = SearchQueryRewriter.from_planning_context(ctx, state).plan_items(max_items=4)
    queries = [i.search_query for i in items]
    assert len(queries) >= 2
    assert all("束河古镇" in q for q in queries)
    goals = {i.search_goal for i in items}
    assert len(goals) >= 2
