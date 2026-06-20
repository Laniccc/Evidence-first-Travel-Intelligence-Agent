import pytest

from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.user_query import TravelAgentState
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.conversation_context import ConversationContext
from app.schemas.evidence import ClaimType, SourceType
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.semantic_frame import AnswerMode, DecisionType, QueryScope, TimeScope
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.tools.knowledge_prior_tool import KnowledgePriorTool, MODEL_PRIOR_LIMITATION


def _qu_result(raw: str, task: TravelTask, **kwargs) -> QueryUnderstandingResult:
    return QueryUnderstandingResult(
        rewritten_query=task.rewritten_query or raw,
        travel_task=task,
        confidence=kwargs.get("confidence", 0.85),
        key_concerns=task.key_concerns,
        **{k: v for k, v in kwargs.items() if k != "confidence"},
    )


@pytest.mark.asyncio
async def test_response_exposes_semantic_frame_and_answer_mode():
    sm = TravelAgentStateMachine()
    resp = await sm.run("札幌适合几月份去？")
    assert resp.answer_mode == "model_prior_allowed"
    assert resp.semantic_frame_summary is not None
    assert resp.semantic_frame_summary["query_scope"] == "city"
    assert resp.semantic_frame_summary["decision_type"] == "best_time_to_visit"
    assert "best_time_to_visit" in resp.semantic_frame_summary["information_needs"]


def test_query_understanding_result_serializes_semantic_frame():
    from app.agents.rule_based_understanding import RuleBasedUnderstanding
    from app.schemas.conversation_context import ConversationContext

    qu = RuleBasedUnderstanding.understand("札幌适合几月份去？", ConversationContext())
    dumped = qu.model_dump()
    assert "semantic_frame" in dumped
    assert dumped["semantic_frame"] is not None
    assert dumped["semantic_frame"]["decision_type"] == "best_time_to_visit"
    restored = QueryUnderstandingResult.model_validate(dumped)
    assert restored.semantic_frame is not None
    assert restored.semantic_frame.query_scope.value == "city"


def test_travel_agent_state_has_semantic_routing_fields():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    assert state.semantic_frame is None
    assert state.answer_mode_decision is None


def test_model_prior_enums_importable():
    assert SourceType.MODEL_PRIOR.value == "model_prior"
    assert ClaimType.SEASONALITY.value == "seasonality"
    assert ClaimType.TRAVEL_ADVICE.value == "travel_advice"
    assert ClaimType.BEST_TIME_TO_VISIT.value == "best_time_to_visit"
    assert KnowledgePriorTool.name == "knowledge_prior"


def test_rule_based_qu_attaches_semantic_frame_for_sapporo():
    from app.agents.rule_based_understanding import RuleBasedUnderstanding
    from app.schemas.conversation_context import ConversationContext

    raw = "札幌适合几月份去？"
    qu = RuleBasedUnderstanding.understand(raw, ConversationContext())
    assert qu.semantic_frame is not None
    sf = qu.semantic_frame
    assert sf.query_scope == QueryScope.CITY
    assert sf.decision_type == DecisionType.BEST_TIME_TO_VISIT
    assert sf.information_needs == ["best_time_to_visit", "seasonality"]
    assert sf.can_answer_with_model_prior is True
    assert sf.requires_exact_fact is False
    assert sf.requires_live_data is False


def test_semantic_frame_sapporo_best_time():
    raw = "札幌适合几月份去？"
    task = TravelTask(
        task_type=TravelTaskType.OPEN_ENDED_ADVICE,
        rewritten_query="Sapporo 最佳出行季节/月份建议",
        country="Japan",
        city="Sapporo",
        key_concerns=["seasonality"],
    )
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    assert frame.query_scope == QueryScope.CITY
    assert frame.entities.country == "Japan"
    assert frame.entities.city == "Sapporo"
    assert frame.decision_type == DecisionType.BEST_TIME_TO_VISIT
    assert frame.time_scope == TimeScope.SEASONAL
    assert frame.requires_live_data is False
    assert frame.requires_exact_fact is False
    assert frame.can_answer_with_model_prior is True
    assert frame.needs_clarification is False


def test_answer_mode_model_prior_allowed_for_destination_season():
    raw = "札幌适合几月份去？"
    task = TravelTask(
        task_type=TravelTaskType.OPEN_ENDED_ADVICE,
        country="Japan",
        city="Sapporo",
        key_concerns=["seasonality"],
    )
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    decision = AnswerModeRouter().route(frame)
    assert decision.answer_mode == AnswerMode.MODEL_PRIOR_ALLOWED
    assert decision.allow_knowledge_prior is True


@pytest.mark.asyncio
async def test_knowledge_prior_tool_generates_low_confidence_evidence():
    raw = "札幌适合几月份去？"
    task = TravelTask(country="Japan", city="Sapporo", task_type=TravelTaskType.OPEN_ENDED_ADVICE)
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    tool = KnowledgePriorTool()
    evidence = await tool.run(raw_query=raw, semantic_frame=frame)
    assert evidence
    ev = evidence[0]
    assert ev.source_type == SourceType.MODEL_PRIOR
    assert ev.claims[0].claim_type == ClaimType.BEST_TIME_TO_VISIT
    assert ev.confidence <= 0.6
    assert ev.retrieved_at is not None
    assert MODEL_PRIOR_LIMITATION in ev.limitations


@pytest.mark.asyncio
async def test_knowledge_prior_does_not_generate_opening_hours():
    raw = "清水寺今天几点关门？"
    task = TravelTask(
        task_type=TravelTaskType.PLACE_FACT_LOOKUP,
        country="Japan",
        city="Kyoto",
        places=[],
        key_concerns=["opening_hours"],
    )
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    frame.information_needs = ["opening_hours"]
    tool = KnowledgePriorTool()
    with pytest.raises(ValueError, match="cannot generate"):
        await tool.run(raw_query=raw, semantic_frame=frame)


def test_opening_hours_requires_evidence():
    raw = "清水寺今天几点关门？"
    task = TravelTask(
        task_type=TravelTaskType.PLACE_FACT_LOOKUP,
        country="Japan",
        city="Kyoto",
        key_concerns=["opening_hours"],
    )
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    decision = AnswerModeRouter().route(frame)
    assert decision.answer_mode == AnswerMode.EVIDENCE_REQUIRED
    assert decision.allow_knowledge_prior is False
    assert EvidencePolicy.model_prior_allowed_for("opening_hours") is False


@pytest.mark.asyncio
async def test_city_level_question_not_blocked_by_missing_place():
    sm = TravelAgentStateMachine()
    resp = await sm.run("札幌适合几月份去？")
    assert resp.answer
    assert resp.confidence > 0
    assert "请提供具体景点" not in resp.answer


@pytest.mark.asyncio
async def test_sapporo_best_month_answer_does_not_ask_for_place():
    sm = TravelAgentStateMachine()
    resp = await sm.run("札幌适合几月份去？")
    assert "景点" not in resp.answer or "1" in resp.answer or "月" in resp.answer
    assert any(m in resp.answer for m in ["1", "2", "6", "8", "9", "10", "月", "冬", "夏"])


@pytest.mark.asyncio
async def test_model_prior_answer_contains_limitations():
    sm = TravelAgentStateMachine()
    resp = await sm.run("札幌适合几月份去？")
    joined = resp.answer + " ".join(resp.limitations)
    assert "一般" in joined or "季节" in joined or "常识" in joined


def test_current_crowd_does_not_use_model_prior():
    assert EvidencePolicy.model_prior_allowed_for("current_crowd") is False
    raw = "清水寺今天人多吗？"
    task = TravelTask(
        task_type=TravelTaskType.CROWD_INQUIRY,
        country="Japan",
        city="Kyoto",
        key_concerns=["crowd_level"],
    )
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    decision = AnswerModeRouter().route(frame)
    assert decision.answer_mode in {AnswerMode.ESTIMATION_ALLOWED, AnswerMode.EVIDENCE_REQUIRED}
    assert decision.allow_knowledge_prior is False


def test_weather_today_requires_weather_api():
    assert EvidencePolicy.model_prior_allowed_for("weather_today") is False
    raw = "京都今天下雨吗？"
    task = TravelTask(
        task_type=TravelTaskType.WEATHER_RISK,
        country="Japan",
        city="Kyoto",
        key_concerns=["weather"],
    )
    frame = SemanticFrameBuilder.build(raw, _qu_result(raw, task))
    decision = AnswerModeRouter().route(frame)
    assert decision.answer_mode == AnswerMode.EVIDENCE_REQUIRED
    assert "weather" in decision.required_tools
