"""S5 whitelist + PolicyGuard acceptance tests for agent-python."""

import pytest

from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.semantic_frame import (
    AnswerMode,
    AnswerModeDecision,
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_query import TravelAgentState, UserGoal
from app.tools.registry import ToolRegistry


def _kanas_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="喀纳斯湖适合几月份去",
        normalized_request="喀纳斯湖最佳出行月份",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", city="Altay", places=["喀纳斯湖"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit", "seasonality"],
        confidence=0.9,
        requires_live_data=False,
        requires_exact_fact=False,
        can_answer_with_model_prior=True,
    )


def _opening_hours_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="清水寺今天几点关门",
        normalized_request="清水寺今日闭馆时间",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="Japan", city="Kyoto", places=["清水寺"]),
        time_scope=TimeScope.CURRENT,
        information_needs=["opening_hours"],
        confidence=0.9,
        requires_live_data=True,
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )


def test_kanas_best_time_whitelist_includes_mcp_and_prior(monkeypatch):
    monkeypatch.setenv("USE_JAVA_TOOL_GATEWAY", "true")
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal advisory",
    )
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    names = set(wl.allowed_tool_names())
    for tool in ("search_mcp", "openmeteo_mcp", "osm_mcp", "knowledge_prior", "fallback"):
        assert tool in names, f"{tool} missing from {names}"


def test_opening_hours_whitelist_excludes_knowledge_prior():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.EVIDENCE_REQUIRED,
        allow_knowledge_prior=False,
        reason="hard fact",
    )
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    names = set(wl.allowed_tool_names())
    assert "knowledge_prior" not in names
    assert "knowledge_prior" in wl.blocked_tools or "knowledge_prior" in wl.reason_by_tool


def test_policy_guard_rejects_tool_outside_dynamic_whitelist():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="restaurant")
    with pytest.raises(ValueError, match="not in dynamic whitelist"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_policy_guard_rejects_knowledge_prior_for_opening_hours():
    from app.schemas.tool_whitelist import ToolDescriptor

    guard = EvidencePolicyGuard()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    wl.allowed_tools.append(
        ToolDescriptor(name="knowledge_prior", description="test", configured=True)
    )
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="knowledge_prior",
        arguments={"information_need": "opening_hours"},
    )
    with pytest.raises(ValueError, match="knowledge_prior cannot satisfy"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_model_prior_queue_tries_tools_before_knowledge_prior():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="test",
    )
    queue = ActionModelController()._evidence_tool_queue(state, {})
    assert queue[0] in {
        "weather",
        "seasonality",
        "search_mcp",
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "baidu_geocode_mcp",
    }
    assert "knowledge_prior" in queue
    assert queue.index("knowledge_prior") > 0


@pytest.mark.asyncio
async def test_tool_trace_marks_s5_llm_selection_and_whitelist():
    from app.orchestrator.action_model_controller import ActionModelController

    class LlmPickWeather(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            prompt_context["_last_action_source"] = "llm"
            if policy.state_name == "evidence_planning_and_tool_use" and step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="weather",
                    arguments={},
                    reason_summary="LLM chose weather from whitelist",
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="China", city="Altay")
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    state.user_goal = UserGoal(destination_country="China", destination_city="Altay")

    tools = ToolRegistry()
    s5 = EvidencePlanningAndToolUseState(llm_client=None, tools=tools)
    s5.runner.model_controller = LlmPickWeather()
    out = await s5.run(state)
    assert out.tool_traces
    trace = out.tool_traces[0]
    assert trace.whitelist_checked is True
    assert trace.selected_by_llm is True
    assert trace.requested_by_state == "evidence_planning_and_tool_use"


def test_s5_prompt_exposes_only_dynamic_allowed_tools():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="China", city="Altay")
    s5 = EvidencePlanningAndToolUseState(llm_client=None, tools=ToolRegistry())
    wl = s5.whitelist_builder.build(state)
    ctx = s5._build_prompt_context(state, {}, wl)
    allowed_names = {t["name"] for t in ctx["allowed_tools"]}
    assert allowed_names == set(wl.allowed_tool_names())
    assert "candidate_tool_plan" not in ctx
    assert "capability_summary" not in ctx
