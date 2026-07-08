"""P5: main pipeline integration tests — SemanticFrame → AnswerMode → Tools → Compose."""

import inspect
import re
from unittest.mock import MagicMock, patch

import pytest

from app.agents.answer_composer_agent import AnswerComposerAgent
from app.agents.rule_based_understanding import RuleBasedUnderstanding
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.llm_client import LLMClient
from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.policy_guard import PolicyGuard
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.orchestrator.state_policy import QUERY_UNDERSTANDING_POLICY
from app.orchestrator.states.query_understanding_state import QueryUnderstandingPromptState
from app.schemas.conversation_context import ConversationContext
from app.schemas.evidence import SourceType
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.semantic_frame import AnswerMode
from app.schemas.user_query import TravelAgentState, UserContext
from app.tools import ToolRegistry
from app.tools.hybrid_tool import HybridTravelTool
from app.tools.knowledge_prior_tool import KnowledgePriorTool, MODEL_PRIOR_LIMITATION


SAPPORO_QUERY = "札幌适合几月份去？"
SEASON_MONTH_MARKERS = ["1", "2", "6", "8", "9", "10", "月", "冬", "夏"]
LIMITATION_MARKERS = ["一般", "季节", "常识", "规律", "具体年份", "天气", "价格", "活动"]


# --- Schema / state fields ---


def test_state_has_semantic_frame_and_answer_mode_fields():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    assert hasattr(state, "semantic_frame")
    assert hasattr(state, "answer_mode_decision")
    assert state.semantic_frame is None
    assert state.answer_mode_decision is None


def test_query_understanding_result_contains_semantic_frame():
    qu = RuleBasedUnderstanding.understand(SAPPORO_QUERY, ConversationContext())
    dumped = qu.model_dump()
    assert "semantic_frame" in dumped
    assert dumped["semantic_frame"] is not None
    assert dumped["semantic_frame"]["decision_type"] == "best_time_to_visit"
    restored = QueryUnderstandingResult.model_validate(dumped)
    assert restored.semantic_frame is not None
    assert restored.semantic_frame.query_scope.value == "city"


@pytest.mark.asyncio
async def test_query_understanding_state_writes_semantic_frame_to_state():
    qu_state = QueryUnderstandingPromptState(LLMClient())
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=SAPPORO_QUERY)
    out = await qu_state.run(state, UserContext())
    assert out.semantic_frame is not None
    assert out.semantic_frame.query_scope.value == "city"
    assert out.semantic_frame.decision_type.value == "best_time_to_visit"
    assert out.query_understanding is not None
    assert any("LLM 用户理解" in t or "NormalizedUserRequest" in t for t in out.visible_trace)


# --- AnswerMode in state machine ---


@pytest.mark.asyncio
async def test_answer_mode_router_called_in_state_machine():
    sm = TravelAgentStateMachine()
    with patch.object(
        sm.answer_mode_router,
        "route",
        wraps=sm.answer_mode_router.route,
    ) as route_mock:
        resp = await sm.run(SAPPORO_QUERY)
    route_mock.assert_called_once()
    assert resp.answer_mode == "model_prior_allowed"
    assert "已判定回答模式" in " ".join(resp.visible_trace)


@pytest.mark.asyncio
async def test_sapporo_best_time_goes_to_model_prior_before_place_check():
    sm = TravelAgentStateMachine()
    with patch.object(sm, "_run_single", new_callable=MagicMock) as single_mock:
        resp = await sm.run(SAPPORO_QUERY)
    single_mock.assert_not_called()
    assert resp.answer_mode == "model_prior_allowed"
    assert "请提供具体景点" not in resp.answer
    trace = " ".join(resp.visible_trace)
    # AnswerMode routing must appear before UserGoal / place pipeline markers
    am_idx = trace.find("已判定回答模式")
    ug_idx = trace.find("识别用户画像")
    assert am_idx >= 0
    assert ug_idx == -1 or am_idx < ug_idx
    # prior_advisory may invoke knowledge_prior via S5 loop or only as fallback — e2e covers full prior usage
    prior_used = any(t.get("tool_name") == "knowledge_prior" for t in resp.tool_traces) or any(
        e.get("source_type") == "model_prior" for e in (resp.evidence_summary or [])
    )
    assert prior_used or "MODEL_PRIOR_ALLOWED" in trace


# --- Tool registry ---


def test_knowledge_prior_tool_registered():
    tools = ToolRegistry(use_mock=True)
    assert hasattr(tools, "knowledge_prior")
    assert tools.knowledge_prior.name == "knowledge_prior"
    assert "knowledge_prior" in tools.registered_tool_names()


def test_tool_registry_accepts_llm_client():
    llm = LLMClient()
    tools = ToolRegistry(llm_client=llm, use_mock=True)
    assert tools.llm is llm
    assert tools.knowledge_prior is not None


def test_registry_hybrid_mode_registers_real_and_mock_fallback():
    tools = ToolRegistry(tool_mode="hybrid")
    assert tools.tool_mode == "hybrid"
    for name in ("official", "places", "weather"):
        wrapped = getattr(tools, name)
        assert isinstance(wrapped, HybridTravelTool)
        assert wrapped.allow_mock_fallback is True
        assert wrapped.real_tool is not None
        assert wrapped.mock_tool is not None


# --- Claude state runner ---


def test_llm_client_is_not_used_as_tool_loop_yet_or_state_runner_exists():
    from app.orchestrator.states import llm_understanding_state as qu_mod

    assert ClaudeStateRunner is not None
    assert "LLMUnderstandingState" in inspect.getsource(qu_mod)
    registry_source = inspect.getsource(ToolRegistry)
    assert "ClaudeStateRunner" not in registry_source


@pytest.mark.asyncio
async def test_state_runner_action_loop_max_steps():
    from app.orchestrator.action_model_controller import ActionModelController
    from app.orchestrator.actions import AgentAction, AgentActionType
    from app.schemas.conversation_context import ConversationContext

    class StuckController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            return AgentAction(
                action_type=AgentActionType.UPDATE_STATE,
                arguments={"noop": True},
                reason_summary="never finish",
            )

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    state.conversation_context = ConversationContext()
    runner = ClaudeStateRunner(model_controller=StuckController())
    out = await runner.run(state, QUERY_UNDERSTANDING_POLICY, {"user_ctx": UserContext()})
    assert any("reached max_steps" in lim for lim in out.limitations)


def test_claude_state_runner_rejects_disallowed_tool():
    from app.orchestrator.actions import AgentAction, AgentActionType

    guard = PolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="weather")
    with pytest.raises(ValueError, match="not allowed"):
        guard.validate(action, QUERY_UNDERSTANDING_POLICY)


@pytest.mark.asyncio
async def test_composer_does_not_generate_unsupported_hard_facts():
    frame = SemanticFrameBuilder.build_city_best_time(
        raw_query=SAPPORO_QUERY,
        country="Japan",
        city="Sapporo",
        rewritten_query=SAPPORO_QUERY,
        confidence=0.85,
    )
    evidence = await KnowledgePriorTool().run(raw_query=SAPPORO_QUERY, semantic_frame=frame)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=SAPPORO_QUERY)
    state.evidence = evidence
    state.limitations.append(MODEL_PRIOR_LIMITATION)

    draft = await AnswerComposerAgent().compose(
        state,
        {"compose_mode": "advisory", "target_label": "Sapporo"},
    )
    text = draft.render_text()
    assert not re.search(r"\d{1,2}:\d{2}", text), "composer invented opening hours"
    assert not re.search(r"\d+\s*(?:JPY|CNY|元)", text), "composer invented ticket price"
    assert draft.cited_evidence_ids


# --- Acceptance: 札幌适合几月份去？ ---


@pytest.mark.asyncio
async def test_sapporo_best_time_acceptance_end_to_end():
    """Full main-chain acceptance for city-level seasonal advisory."""
    sm = TravelAgentStateMachine()
    resp = await sm.run(SAPPORO_QUERY)

    # 1. 不要求具体景点
    assert "请提供具体景点" not in resp.answer

    # 2–4. SemanticFrame + AnswerMode exposed on response
    assert resp.semantic_frame_summary is not None
    assert resp.semantic_frame_summary["query_scope"] == "city"
    assert resp.semantic_frame_summary["decision_type"] == "best_time_to_visit"
    assert resp.answer_mode == "model_prior_allowed"

    # 5. knowledge_prior invoked
    assert any(
        t.get("tool_name") == "knowledge_prior" and t.get("status") == "ok" for t in resp.tool_traces
    )
    assert resp.evidence_summary
    assert any(e.get("source_type") == SourceType.MODEL_PRIOR.value for e in resp.evidence_summary)

    # 6. Seasonal month guidance in answer
    assert any(m in resp.answer for m in SEASON_MONTH_MARKERS)

    # 7. Limitations disclose low-confidence / non-real-time nature
    joined = resp.answer + " ".join(resp.limitations)
    assert any(m in joined for m in LIMITATION_MARKERS)
    assert MODEL_PRIOR_LIMITATION in joined or "一般" in joined

    # Router decision sanity
    decision = AnswerModeRouter().route(
        SemanticFrameBuilder.build_city_best_time(
            raw_query=SAPPORO_QUERY,
            country="Japan",
            city="Sapporo",
            rewritten_query=SAPPORO_QUERY,
            confidence=0.85,
        )
    )
    assert decision.answer_mode == AnswerMode.MODEL_PRIOR_ALLOWED
