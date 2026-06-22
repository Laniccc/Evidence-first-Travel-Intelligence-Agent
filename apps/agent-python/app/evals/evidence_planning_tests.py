import pytest

from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.policy_guard import PolicyGuard
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
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
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.tools import ToolRegistry
from app.tools.tool_name_resolver import resolve_tool_name
from app.evals.mcp_evidence_planning_tests import _patch_search_only_settings


def _hokkaido_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="北海道适合几月份去",
        normalized_request="北海道最佳出行月份",
        query_scope=QueryScope.REGION,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="Japan", city="Hokkaido", places=[]),
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


def test_evidence_planning_and_tool_use_state_exists():
    assert EvidencePlanningAndToolUseState is not None
    assert EVIDENCE_PLANNING_AND_TOOL_USE_POLICY.state_name == "evidence_planning_and_tool_use"


def test_evidence_planning_state_uses_claude_runner():
    state_obj = EvidencePlanningAndToolUseState(llm_client=None, tools=ToolRegistry())
    assert isinstance(state_obj.runner, ClaudeStateRunner)
    assert isinstance(state_obj.runner.policy_guard, EvidencePolicyGuard)


@pytest.mark.asyncio
async def test_llm_can_update_information_needs_inside_state():
    class UpdateNeedsController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if step == 0:
                return AgentAction(
                    action_type=AgentActionType.UPDATE_STATE,
                    arguments={
                        "information_needs": [
                            {
                                "need_type": "weather",
                                "priority": "high",
                                "reason": "seasonal planning",
                            }
                        ],
                        "planning_notes": ["LLM revised needs"],
                    },
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")

    runner = ClaudeStateRunner(model_controller=UpdateNeedsController(), tools=ToolRegistry())
    out = await runner.run(state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, {})
    assert out.information_needs
    assert out.information_needs[0].need_type.value == "weather"
    assert any("UPDATE_STATE" in t for t in out.visible_trace)


@pytest.mark.asyncio
async def test_llm_can_choose_multiple_tools():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal advisory",
    )
    state.user_goal = UserGoal(destination_country="Japan", destination_city="Hokkaido")

    tools = ToolRegistry()
    out = await EvidencePlanningAndToolUseState(llm_client=None, tools=tools).run(state)
    tool_names = {t.tool_name for t in out.tool_traces}
    assert len(tool_names) >= 2
    assert any("受控状态循环：evidence_planning_and_tool_use" in t for t in out.visible_trace)


def test_policy_guard_rejects_disallowed_tool():
    guard = PolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="not_a_real_tool")
    with pytest.raises(ValueError, match="not allowed"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY)


def test_knowledge_prior_forbidden_for_opening_hours_legacy():
    guard = EvidencePolicyGuard()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="knowledge_prior",
        arguments={"information_need": "opening_hours"},
    )
    with pytest.raises(ValueError, match="knowledge_prior cannot satisfy"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_hokkaido_best_time_not_forced_to_fixed_toolrouter():
    ctrl = ActionModelController()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="test",
    )
    queue = ctrl._evidence_tool_queue(state, {})
    assert queue[0] == "search_mcp"
    assert "openmeteo_mcp" in queue or "climate_mcp" in queue
    assert "knowledge_prior" in queue
    assert queue.index("knowledge_prior") > queue.index("search_mcp")


def test_evidence_required_cannot_finish_without_required_evidence():
    guard = EvidencePolicyGuard()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.EVIDENCE_REQUIRED,
        allow_knowledge_prior=False,
        reason="exact fact",
    )
    action = AgentAction(action_type=AgentActionType.FINISH_STATE, arguments={})
    with pytest.raises(ValueError, match="Cannot FINISH"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


@pytest.mark.asyncio
async def test_model_prior_allowed_can_fallback_to_knowledge_prior():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    state.user_goal = UserGoal(destination_country="Japan", destination_city="Hokkaido")

    class PriorOnlyController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if policy.state_name == "evidence_planning_and_tool_use":
                if step == 0:
                    return AgentAction(
                        action_type=AgentActionType.CALL_TOOL,
                        target="knowledge_prior",
                        arguments={"information_need": "best_time_to_visit"},
                        reason_summary="fallback knowledge_prior",
                    )
                return AgentAction(action_type=AgentActionType.FINISH_STATE)
            return await super().next_action(state, policy, prompt_context, step)

    tools = ToolRegistry()
    wl = ToolWhitelistBuilder(tools_registry=tools).build(state)
    ctx = {
        "tool_whitelist": wl,
        "allowed_tools": [t.model_dump() for t in wl.allowed_tools],
    }
    runner = ClaudeStateRunner(model_controller=PriorOnlyController(), tools=tools)
    out = await runner.run(state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx)
    assert out.evidence
    assert any(t.tool_name == "knowledge_prior" for t in out.tool_traces)


@pytest.mark.asyncio
async def test_tool_traces_record_loop_steps():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    state.user_goal = UserGoal(destination_country="Japan", destination_city="Hokkaido")

    tools = ToolRegistry()
    out = await EvidencePlanningAndToolUseState(llm_client=None, tools=tools).run(state)
    assert out.tool_traces
    assert any("CALL_TOOL" in t for t in out.visible_trace)
    assert out.evidence_planning_completed


def test_s5_tool_whitelist_for_best_time_to_visit():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    names = set(wl.allowed_tool_names())
    assert "seasonality" in names
    assert "knowledge_prior" in names
    assert "restaurant" not in names
    assert "lodging" not in names
    assert "search_mcp" in names or "search_mcp" in wl.blocked_tools


def test_s5_tool_whitelist_for_opening_hours(monkeypatch):
    _patch_search_only_settings(monkeypatch)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.EVIDENCE_REQUIRED,
        allow_knowledge_prior=False,
        reason="hard fact",
    )
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    names = set(wl.allowed_tool_names())
    assert "search_mcp" in names
    assert "places" in names
    assert "official" not in names
    assert "knowledge_prior" not in names
    assert "knowledge_prior" in wl.blocked_tools or "knowledge_prior" in wl.reason_by_tool


def test_policy_guard_rejects_tool_not_in_dynamic_whitelist():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="restaurant")
    with pytest.raises(ValueError, match="not in dynamic whitelist"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_policy_guard_rejects_knowledge_prior_for_hard_fact():
    from app.schemas.tool_whitelist import ToolDescriptor

    guard = EvidencePolicyGuard()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    # Simulate mis-exposed prior — dynamic whitelist should still block via EvidencePolicy
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


@pytest.mark.asyncio
async def test_llm_can_choose_allowed_mcp_from_whitelist():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    tools = ToolRegistry()
    wl = ToolWhitelistBuilder(tools_registry=tools).build(state)
    mcp_targets = [n for n in wl.allowed_tool_names() if n.endswith("_mcp") or n == "search_mcp"]
    if not mcp_targets:
        pytest.skip("No configured MCP tools in this environment")

    chosen = mcp_targets[0]

    class McpController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if policy.state_name == "evidence_planning_and_tool_use" and step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target=chosen,
                    arguments={"query": state.raw_user_query},
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {
        "tool_whitelist": wl,
        "allowed_tools": [t.model_dump() for t in wl.allowed_tools],
    }
    runner = ClaudeStateRunner(model_controller=McpController(), tools=tools)
    out = await runner.run(state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx)
    assert any(
        chosen == t.tool_name or resolve_tool_name(chosen) == t.tool_name for t in out.tool_traces
    )


def test_unconfigured_mcp_not_exposed_to_llm(monkeypatch):
    from app.config import get_settings

    settings = get_settings().model_copy(update={"mcp_enabled": False})
    monkeypatch.setattr("app.orchestrator.tool_whitelist_builder.get_settings", lambda: settings)

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    exposed = wl.allowed_tool_names()
    assert "search_mcp" not in exposed
    assert "openmeteo_mcp" not in exposed
    assert "official_page_reader_mcp" not in exposed


def test_s5_prompt_contains_only_allowed_tools():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    s5 = EvidencePlanningAndToolUseState(llm_client=None, tools=ToolRegistry())
    wl = s5.whitelist_builder.build(state)
    ctx = s5._build_prompt_context(state, {}, wl)
    allowed_names = {t["name"] for t in ctx["allowed_tools"]}
    assert "restaurant" not in allowed_names
    assert "lodging" not in allowed_names
    assert allowed_names == set(wl.allowed_tool_names())


@pytest.mark.asyncio
async def test_tool_trace_marks_selected_by_llm_and_whitelist_checked():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    state.user_goal = UserGoal(destination_country="Japan", destination_city="Hokkaido")

    tools = ToolRegistry()
    out = await EvidencePlanningAndToolUseState(llm_client=None, tools=tools).run(state)
    assert out.tool_traces
    trace = out.tool_traces[0]
    assert trace.whitelist_checked is True
    assert trace.requested_by_state == "evidence_planning_and_tool_use"
