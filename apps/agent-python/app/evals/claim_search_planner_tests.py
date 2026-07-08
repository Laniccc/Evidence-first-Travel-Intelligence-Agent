"""Tests for S5 search planning helpers and LLM task planner."""

import json

import pytest

from app.agents.search_task_planner_agent import SearchTaskPlannerAgent, _planner_user_payload
from app.evals.llm_test_helpers import StubLLMClient, duku_search_tasks_json
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.actions import ActionResult, AgentAction, AgentActionType
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.state_reducer import StateReducer
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.place_ambiguity import PlaceAmbiguityCandidate, PlaceAmbiguityInfo
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


def test_planning_context_includes_s2_place_ambiguity():
    frame = _duku_frame(
        raw_query="衡山景区票价如何？",
        normalized_request="衡山景区门票价格",
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["衡山"]),
        information_needs=["ticket_price"],
        place_ambiguity=PlaceAmbiguityInfo(
            is_ambiguous=True,
            reason="衡山可能指南岳衡山或北岳恒山",
            candidates=[
                PlaceAmbiguityCandidate(name="南岳衡山", region="湖南", city="衡阳"),
            ],
        ),
        labeled_entities=[
            {
                "text": "衡山",
                "normalized_name": "衡山",
                "labels": ["primary_subject"],
            }
        ],
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="衡山景区票价如何？")
    state.semantic_frame = frame
    state.response_contract = ResponseContractCompiler().compile(frame)

    ctx = ClaimSearchPlanner.planning_context(state)
    assert ctx["place_ambiguity"]["is_ambiguous"] is True
    assert "南岳衡山" in ctx["gated_search_keywords"]
    assert ctx["labeled_entities"]


def test_insufficient_keyword_search_not_counted_as_effective_query():
    frame = SemanticFrame(
        raw_query="栖霞山门票价格多少？",
        normalized_request="栖霞山门票价格",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["栖霞山"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.response_contract = ResponseContractCompiler().compile(frame)
    ev = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://www.ly.com/scenery/BookSceneryTicket_132.html",
        country="China",
        place_name="栖霞山",
        claims=[
            Claim(
                claim_type=ClaimType.TICKET_RELATED_MENTIONS,
                value="栖霞山门票预订，同程旅行，您好，请 登录 免费",
                confidence=0.4,
            )
        ],
        confidence=0.4,
    )
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="keyword_search_agent",
    )
    result = ActionResult(
        ok=True,
        output={
            "task_id": "t-login",
            "claim_target": "ticket_price",
            "information_need": "ticket_price",
            "search_query": "栖霞山 官网 门票",
            "evidence": [ev],
        },
    )

    StateReducer().apply(state, action, result, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY)

    structured = state.structured_result or {}
    assert structured["attempted_search_task_ids"] == ["t-login"]
    assert structured["completed_search_task_ids"] == []
    assert ClaimSearchPlanner.keyword_search_call_count(state) == 0
    assert structured["keyword_search_results"][-1]["counted_as_effective_query"] is False


def test_planner_user_payload_includes_user_need_residual():
    from app.orchestrator.user_need_residual import attach_user_need_residual

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="今天独库公路能走吗？")
    state.semantic_frame = SemanticFrame(
        raw_query="今天独库公路能走吗？",
        normalized_request="独库公路今日通行状态",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(places=["独库公路"], region="新疆"),
        time_scope=TimeScope.CURRENT,
        information_needs=["seasonal_operation_status"],
        requires_live_data=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    attach_user_need_residual(state)

    ctx = ClaimSearchPlanner.planning_context(state)
    payload = _planner_user_payload(ctx, refine=False)
    assert payload.get("user_need_residual") is not None
    assert payload["user_need_residual"]["time_scope"] == "current"
    assert any(
        n["need_type"] == "seasonal_operation_status"
        for n in payload["user_need_residual"]["information_needs"]
    )


def test_s5_prompt_context_includes_user_need_residual():
    from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
    from app.orchestrator.user_need_residual import attach_user_need_residual
    from app.schemas.tool_whitelist import ToolWhitelist

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="今天独库公路能走吗？")
    state.semantic_frame = SemanticFrame(
        raw_query="今天独库公路能走吗？",
        normalized_request="独库公路今日通行状态",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(places=["独库公路"], region="新疆"),
        time_scope=TimeScope.CURRENT,
        information_needs=["seasonal_operation_status"],
        requires_live_data=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    attach_user_need_residual(state)

    wl = ToolWhitelist(state_name="evidence_planning_and_tool_use", allowed_tools=[])
    ctx = EvidencePlanningAndToolUseState()._build_prompt_context(state, {}, wl)
    assert ctx.get("user_need_residual") is not None
    assert ctx["user_need_residual"]["time_scope"] == "current"
    assert any("orchestrator" in rule.lower() for rule in ctx.get("s5_prompt_rules", []))
    assert ctx.get("subagent_definitions")


@pytest.mark.asyncio
async def test_search_task_planner_uses_llm_tasks():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    llm = StubLLMClient(lambda _s, _u: duku_search_tasks_json())
    tasks = await SearchTaskPlannerAgent(llm).run(state)
    assert len(tasks) >= 2
    assert all(t.anchor_keywords for t in tasks)
    assert any("独库公路" in t.search_query for t in tasks)


def test_max_search_attempts_for_required_claims():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    assert ClaimSearchPlanner.max_search_attempts(state) == 4


def test_contract_whitelist_allows_knowledge_prior_for_optional_context():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="新疆的独库公路每年几月份开放？")
    state.semantic_frame = _duku_frame()
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    wl = ToolWhitelistBuilder().build(state)
    assert "knowledge_prior" in wl.allowed_tool_names()


@pytest.mark.asyncio
async def test_search_task_planner_accepts_new_tasks_key_on_refine():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="南岳衡山门票多少钱")
    state.semantic_frame = SemanticFrame(
        raw_query="南岳衡山门票多少钱",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["南岳衡山", "衡山"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    payload = json.dumps(
        {
            "new_tasks": [
                {
                    "anchor_keywords": ["衡山", "门票", "观光车", "索道", "价格"],
                    "search_query": "衡山门票 包含 观光车 索道 价格",
                    "information_need": "ticket_price",
                    "preferred_tool": "search_mcp",
                }
            ]
        },
        ensure_ascii=False,
    )
    tasks = await SearchTaskPlannerAgent(StubLLMClient(lambda _s, _u: payload)).run(
        state, refine=True
    )
    assert tasks
    assert "衡山" in tasks[0].search_query


@pytest.mark.asyncio
async def test_search_task_planner_coerces_missing_anchors_in_query():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="白沙湖的海拔多少？")
    state.semantic_frame = SemanticFrame(
        raw_query="白沙湖的海拔多少？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["白沙湖"]),
        information_needs=["general_information"],
        requires_exact_fact=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    # LLM returns query without explicit anchor tokens in search_query text.
    bad = json.dumps(
        {
            "tasks": [
                {
                    "anchor_keywords": ["白沙湖", "海拔"],
                    "search_query": "高度是多少",
                    "information_need": "general_travel_advice",
                }
            ]
        },
        ensure_ascii=False,
    )
    tasks = await SearchTaskPlannerAgent(StubLLMClient(lambda _s, _u: bad)).run(state)
    assert tasks
    assert tasks[0].search_query.startswith("白沙湖")
    assert "海拔" in tasks[0].anchor_keywords


@pytest.mark.asyncio
async def test_search_task_planner_repairs_after_empty_task_list():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="白沙湖的海拔多少？")
    state.semantic_frame = SemanticFrame(
        raw_query="白沙湖的海拔多少？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["白沙湖"]),
        information_needs=["general_information"],
        requires_exact_fact=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    repaired = json.dumps(
        {
            "tasks": [
                {
                    "anchor_keywords": ["白沙湖", "海拔"],
                    "search_query": "白沙湖海拔",
                    "information_need": "general_travel_advice",
                    "preferred_tool": "search_mcp",
                }
            ]
        },
        ensure_ascii=False,
    )
    llm = StubLLMClient(responses=['{"tasks":[]}', repaired])
    tasks = await SearchTaskPlannerAgent(llm).run(state)
    assert tasks
    assert any("白沙湖" in t.search_query for t in tasks)
    assert any("海拔" in t.search_query for t in tasks)


@pytest.mark.asyncio
async def test_search_task_planner_repairs_truncated_json_locally():
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
    repaired = json.dumps(
        {
            "tasks": [
                {
                    "anchor_keywords": ["南京博物院", "门票"],
                    "search_query": "南京博物院门票",
                    "information_need": "ticket_price",
                }
            ]
        },
        ensure_ascii=False,
    )
    llm = StubLLMClient(responses=[broken, repaired])
    tasks = await SearchTaskPlannerAgent(llm).run(state, refine=True)
    assert tasks
    assert any("南京博物院" in t.search_query for t in tasks)
    assert tasks[0].rationale in {"LLM planned", "LLM refine"}
    assert llm._call_count == 2


@pytest.mark.asyncio
async def test_search_task_planner_raises_when_repair_also_fails():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="白沙湖的海拔多少？")
    state.semantic_frame = SemanticFrame(
        raw_query="白沙湖的海拔多少？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["白沙湖"]),
        information_needs=["general_information"],
        requires_exact_fact=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)

    with pytest.raises(ValueError, match="could not produce valid tasks"):
        await SearchTaskPlannerAgent(
            StubLLMClient(responses=['{"tasks":[]}', '{"tasks":[]}'])
        ).run(state, refine=True)


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
