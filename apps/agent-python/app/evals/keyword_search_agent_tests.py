"""Tests for keyword_search_agent as first-party MCP executor with tool catalog."""

from __future__ import annotations

import pytest

from app.agents.keyword_search_agent import KeywordSearchAgent
from app.orchestrator.agent_tool_catalog import agent_tool_definitions_for_allowed
from app.schemas.search_task import SearchTask
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.user_query import TravelAgentState


def _whitelist(*names: str) -> ToolWhitelist:
    return ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[ToolDescriptor(name=n, description=n, configured=True) for n in names],
    )


def test_pick_tool_route_task_from_tool_parameters():
    task = SearchTask(
        task_id="r1",
        lookup_intent="核实乌鲁木齐到可可托海驾车距离与时长",
        claim_target="distance",
        information_need="route_plan",
        search_query="乌鲁木齐 可可托海 驾车",
        anchor_keywords=["乌鲁木齐", "可可托海"],
        preferred_tool="search_mcp",
        tool_parameters={"origin": "乌鲁木齐市", "destination": "可可托海风景区", "mode": "driving"},
    )
    wl = _whitelist("search_mcp", "baidu_route_mcp")
    tool = KeywordSearchAgent.pick_tool(task, wl, agent_tool_definitions_for_allowed(wl.allowed_tool_names()))
    assert tool == "baidu_route_mcp"


def test_pick_tool_uses_catalog_satisfies_needs():
    task = SearchTask(
        task_id="r2",
        lookup_intent="获取景区开放时间",
        claim_target="opening_hours",
        information_need="opening_hours",
        search_query="喀纳斯 开放时间",
        anchor_keywords=["喀纳斯"],
    )
    wl = _whitelist("search_mcp", "official_page_reader_mcp")
    defs = agent_tool_definitions_for_allowed(wl.allowed_tool_names())
    tool = KeywordSearchAgent.pick_tool(task, wl, defs)
    assert tool in {"official_page_reader_mcp", "search_mcp"}


def test_validate_route_task_requires_origin_destination():
    task = SearchTask(
        task_id="bad",
        lookup_intent="算路程",
        claim_target="distance",
        information_need="route_plan",
        preferred_tool="baidu_route_mcp",
        tool_parameters={"origin": "乌鲁木齐市"},
    )
    with pytest.raises(ValueError, match="destination"):
        KeywordSearchAgent.validate_task(task)


def test_build_tool_payload_enriches_route_origin_for_xinjiang_day_trip():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海一天够玩吗？")
    state.semantic_frame = SemanticFrame(
        raw_query="可可托海一天够玩吗？",
        task_family=TaskFamily.SUITABILITY,
        decision_type=DecisionType.WHETHER_TO_GO,
        entities=SemanticEntities(country="China", region="新疆", places=["可可托海风景区"]),
    )
    task = SearchTask(
        task_id="r3",
        lookup_intent="判断乌鲁木齐当日往返可可托海是否可行",
        claim_target="distance",
        information_need="route_plan",
        search_query="乌鲁木齐 可可托海",
        anchor_keywords=["乌鲁木齐", "可可托海"],
        tool_parameters={"destination": "可可托海风景区"},
        preferred_tool="baidu_route_mcp",
    )
    payload = KeywordSearchAgent.build_tool_payload("baidu_route_mcp", task, state, {})
    assert payload.get("destination") == "可可托海风景区"
    assert payload.get("origin") == "乌鲁木齐市"


def test_search_task_requires_lookup_intent_or_query():
    with pytest.raises(ValueError, match="lookup_intent or search_query"):
        KeywordSearchAgent.validate_task(
            SearchTask(task_id="x", lookup_intent="", search_query="", anchor_keywords=["a"])
        )
