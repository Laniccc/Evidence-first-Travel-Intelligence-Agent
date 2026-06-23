"""Tests for S5 search planning helpers and LLM task planner."""

import json

import pytest

from app.agents.search_task_planner_agent import SearchTaskPlannerAgent
from app.evals.llm_test_helpers import StubLLMClient, duku_search_tasks_json
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.user_query import TravelAgentState


def _duku_frame(**kwargs) -> SemanticFrame:
    base = dict(
        raw_query="新疆的独库公路每年几月份开放？",
        normalized_request="新疆独库公路开放月份",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", region="新疆", places=["独库公路"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit"],
    )
    base.update(kwargs)
    return SemanticFrame(**base)


def test_planning_context_includes_user_query_and_claims():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    ctx = ClaimSearchPlanner.planning_context(state)
    assert ctx["raw_query"] == "新疆的独库公路每年几月份开放？"
    assert "独库公路" in str(ctx["entities"])
    assert any("seasonal" in c or "best_time" in c for c in ctx["claim_types"])


@pytest.mark.asyncio
async def test_search_task_planner_uses_llm_tasks():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    llm = StubLLMClient(lambda _s, _u: duku_search_tasks_json())
    tasks = await SearchTaskPlannerAgent(llm).run(state)
    assert len(tasks) >= 2
    assert all(t.anchor_keywords for t in tasks)
    assert tasks[0].search_query == "独库公路什么时候开放"


def test_max_search_attempts_for_required_claims():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    assert ClaimSearchPlanner.max_search_attempts(state) == 6


def test_contract_whitelist_allows_knowledge_prior_for_optional_context():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    wl = ToolWhitelistBuilder().build(state)
    assert "knowledge_prior" in wl.allowed_tool_names()


@pytest.mark.asyncio
async def test_search_task_planner_falls_back_on_invalid_llm_json():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="南京博物院门票多少钱？")
    state.semantic_frame = SemanticFrame(
        raw_query="南京博物院门票多少钱？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="南京", places=["南京博物院"]),
        information_needs=["ticket_price"],
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    broken = '{"tasks":[{"anchor_keywords":["南京博物院"],"search_query":"南京博物院门票'
    llm = StubLLMClient(lambda _s, _u: broken)
    tasks = await SearchTaskPlannerAgent(llm).run(state)
    assert tasks
    assert any("南京博物院" in t.search_query for t in tasks)
    assert tasks[0].rationale.startswith("Rule-based fallback")


@pytest.mark.asyncio
async def test_suitability_planner_stub_respects_user_query():
    frame = SemanticFrame(
        raw_query="南京中山陵适合带父母去吗",
        normalized_request="南京中山陵是否适合带父母",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.SUITABILITY,
        decision_type=DecisionType.WHETHER_TO_GO,
        entities=SemanticEntities(country="China", city="南京", region="江苏", places=["中山陵"]),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=["walking_intensity", "accessibility", "crowd_level"],
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.response_contract = ResponseContractCompiler().compile(frame)

    tasks = await SearchTaskPlannerAgent(StubLLMClient()).run(state)
    assert tasks
    assert all("通车" not in t.search_query for t in tasks)
    assert any("父母" in t.search_query or "中山陵" in t.search_query for t in tasks)
