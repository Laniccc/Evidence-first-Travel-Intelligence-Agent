import pytest

from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.policy_guard import PolicyGuard
from app.orchestrator.state_policy import ANSWER_COMPOSITION_POLICY, QUERY_UNDERSTANDING_POLICY
from app.orchestrator.states.query_understanding_state import QueryUnderstandingPromptState
from app.schemas.user_query import TravelAgentState, UserContext


def test_agent_action_schema():
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="semantic_frame_builder",
        reason_summary="build frame",
    )
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "semantic_frame_builder"


def test_policy_guard_rejects_disallowed_subagent():
    guard = PolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="unknown_agent",
    )
    with pytest.raises(ValueError, match="not allowed"):
        guard.validate(action, QUERY_UNDERSTANDING_POLICY)


def test_policy_guard_rejects_disallowed_tool_in_qu_state():
    guard = PolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="weather")
    with pytest.raises(ValueError, match="not allowed"):
        guard.validate(action, QUERY_UNDERSTANDING_POLICY)


@pytest.mark.asyncio
async def test_claude_state_runner_query_understanding_loop():
    from app.schemas.conversation_context import ConversationContext

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="札幌适合几月份去？")
    state.conversation_context = ConversationContext()
    runner = ClaudeStateRunner()
    state = await runner.run(
        state,
        QUERY_UNDERSTANDING_POLICY,
        {"supported_regions": ["Japan", "China", "South Korea"], "user_ctx": UserContext()},
    )
    assert state.query_understanding is not None
    assert state.semantic_frame is not None
    assert any("受控状态循环" in t for t in state.visible_trace)
    assert any("FINISH_STATE → QueryUnderstandingResult" in t for t in state.visible_trace)


@pytest.mark.asyncio
async def test_qu_finish_state_carries_query_understanding_result():
    from app.schemas.conversation_context import ConversationContext

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="札幌适合几月份去？")
    state.conversation_context = ConversationContext()
    runner = ClaudeStateRunner()
    state = await runner.run(
        state,
        QUERY_UNDERSTANDING_POLICY,
        {"supported_regions": ["Japan"], "user_ctx": UserContext()},
    )
    assert state.query_understanding.rewritten_query
    assert state.semantic_frame.decision_type.value == "best_time_to_visit"


@pytest.mark.asyncio
async def test_query_understanding_state_uses_controlled_loop():
    sm_state = TravelAgentState(session_id="s", query_id="q", raw_user_query="札幌适合几月份去？")
    qu_state = QueryUnderstandingPromptState(llm_client=None)
    out = await qu_state.run(sm_state, UserContext())
    assert out.semantic_frame is not None
    assert any("受控状态循环" in t for t in out.visible_trace)


@pytest.mark.asyncio
async def test_claude_state_runner_answer_composition_loop():
    from app.tools.knowledge_prior_tool import KnowledgePriorTool
    from app.agents.semantic_frame_builder import SemanticFrameBuilder
    from app.schemas.travel_task import TravelTask, TravelTaskType

    raw = "札幌适合几月份去？"
    task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Sapporo")
    frame = SemanticFrameBuilder.build_city_best_time(
        raw_query=raw,
        country="Japan",
        city="Sapporo",
        rewritten_query=raw,
        confidence=0.85,
    )
    tool = KnowledgePriorTool()
    evidence = await tool.run(raw_query=raw, semantic_frame=frame)

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=raw)
    state.evidence = evidence
    state.semantic_frame = frame

    runner = ClaudeStateRunner()
    state = await runner.run(
        state,
        ANSWER_COMPOSITION_POLICY,
        {"compose_mode": "advisory", "target_label": "Sapporo"},
    )
    assert state.final_response
    assert "Sapporo" in state.final_response or "札幌" in state.final_response
    assert state.structured_result and state.structured_result.get("final_answer_draft")
    assert any("FINISH_STATE → FinalAnswerDraft" in t for t in state.visible_trace)


@pytest.mark.asyncio
async def test_answer_composer_produces_final_answer_draft():
    from app.agents.answer_composer_agent import AnswerComposerAgent
    from app.agents.semantic_frame_builder import SemanticFrameBuilder
    from app.schemas.travel_task import TravelTask, TravelTaskType
    from app.tools.knowledge_prior_tool import KnowledgePriorTool

    raw = "札幌适合几月份去？"
    frame = SemanticFrameBuilder.build_city_best_time(
        raw_query=raw,
        country="Japan",
        city="Sapporo",
        rewritten_query=raw,
        confidence=0.85,
    )
    evidence = await KnowledgePriorTool().run(raw_query=raw, semantic_frame=frame)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=raw)
    state.evidence = evidence
    state.limitations.append("测试限制")

    draft = await AnswerComposerAgent().compose(
        state,
        {"compose_mode": "advisory", "target_label": "Sapporo"},
    )
    assert draft.conclusion
    assert draft.cited_evidence_ids
    assert draft.answer_text
    assert "测试限制" in draft.limitations or "测试限制" in draft.answer_text


def test_deterministic_planner_finishes_after_qu():
    ctrl = ActionModelController()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    a0 = ctrl._deterministic_action(state, QUERY_UNDERSTANDING_POLICY, {}, 0)
    assert a0.action_type == AgentActionType.CALL_SUBAGENT
    assert a0.target == "query_understanding"
