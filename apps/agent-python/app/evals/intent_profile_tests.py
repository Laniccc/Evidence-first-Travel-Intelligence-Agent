"""IntentProfile rule derivation + strategy integration tests."""

from __future__ import annotations

import pytest

from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    PrimaryIntent,
)
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.s5_information_domain import InformationDomain
from app.schemas.user_query import TravelAgentState


def _frame(**kwargs) -> SemanticFrame:
    base = dict(
        raw_query="",
        normalized_request="",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.GENERAL_ADVICE,
        entities=SemanticEntities(country="China", city="丽江", places=["束河古镇"]),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=[],
        can_answer_with_model_prior=True,
    )
    base.update(kwargs)
    return SemanticFrame(**base)


@pytest.mark.parametrize(
    "query,needs,kwargs,expected_intent,expected_sensitivity",
    [
        (
            "束河古镇要门票吗",
            ["ticket_price"],
            {
                "decision_type": DecisionType.FACT_LOOKUP,
                "task_family": TaskFamily.FACT_LOOKUP,
                "requires_exact_fact": True,
            },
            PrimaryIntent.LOOKUP,
            EvidenceSensitivity.HARD_FACT,
        ),
        (
            "束河值不值得去",
            ["value_for_money"],
            {
                "decision_type": DecisionType.WHETHER_TO_GO,
                "task_family": TaskFamily.SUITABILITY,
            },
            PrimaryIntent.ADVISORY,
            EvidenceSensitivity.EXPERIENCE_BASED,
        ),
        (
            "独库公路两天够玩吗",
            ["itinerary_feasibility", "duration"],
            {
                "decision_type": DecisionType.ROUTE_PLAN,
                "task_family": TaskFamily.PLANNING,
                "entities": SemanticEntities(country="China", city="伊犁", places=["独库公路"]),
            },
            PrimaryIntent.PLANNING,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
        ),
        (
            "束河 vs 白沙",
            ["value_for_money"],
            {
                "decision_type": DecisionType.HOW_TO_CHOOSE,
                "task_family": TaskFamily.COMPARISON,
                "entities": SemanticEntities(country="China", city="丽江", places=["束河古镇", "白沙古镇"]),
            },
            PrimaryIntent.COMPARISON,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
        ),
        (
            "束河商业化严重吗",
            ["commercialization_risk"],
            {
                "decision_type": DecisionType.GENERAL_ADVICE,
                "task_family": TaskFamily.ADVISORY,
            },
            PrimaryIntent.REVIEW_CHECK,
            EvidenceSensitivity.EXPERIENCE_BASED,
        ),
        (
            "明天可可托海天气",
            ["weather_today", "forecast"],
            {
                "decision_type": DecisionType.FACT_LOOKUP,
                "time_scope": TimeScope.SPECIFIC_DATE,
                "requires_live_data": True,
                "entities": SemanticEntities(country="China", city="阿勒泰", places=["可可托海"]),
            },
            PrimaryIntent.REALTIME_CHECK,
            EvidenceSensitivity.LIVE_REQUIRED,
        ),
        (
            "束河附近好吃的",
            ["nearby_food"],
            {
                "decision_type": DecisionType.NEARBY_SEARCH,
                "task_family": TaskFamily.ADVISORY,
            },
            PrimaryIntent.NEARBY,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
        ),
        (
            "束河古镇附近餐厅",
            ["nearby_dining"],
            {
                "decision_type": DecisionType.NEARBY_SEARCH,
                "task_family": TaskFamily.ADVISORY,
            },
            PrimaryIntent.NEARBY,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
        ),
        (
            "附近有什么好吃的",
            [],
            {
                "decision_type": DecisionType.GENERAL_ADVICE,
                "task_family": TaskFamily.ADVISORY,
                "entities": SemanticEntities(country="China", city="丽江", places=["束河古镇"]),
            },
            PrimaryIntent.NEARBY,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
        ),
        (
            "独库公路几月份开放",
            ["seasonal_operation_status"],
            {
                "decision_type": DecisionType.GENERAL_ADVICE,
                "task_family": TaskFamily.ADVISORY,
                "requires_exact_fact": True,
                "entities": SemanticEntities(country="China", city="伊犁", places=["独库公路"]),
            },
            PrimaryIntent.LOOKUP,
            EvidenceSensitivity.HARD_FACT,
        ),
        (
            "今天能走吗",
            [],
            {
                "time_scope": TimeScope.CURRENT,
                "entities": SemanticEntities(country="China", city="伊犁", places=["独库公路"]),
            },
            PrimaryIntent.REALTIME_CHECK,
            EvidenceSensitivity.LIVE_REQUIRED,
        ),
        (
            "独库公路几月份开放",
            ["seasonal_operation_status"],
            {
                "decision_type": DecisionType.FACT_LOOKUP,
                "task_family": TaskFamily.FACT_LOOKUP,
                "requires_exact_fact": True,
                "entities": SemanticEntities(country="China", city="伊犁", places=["独库公路"]),
            },
            PrimaryIntent.LOOKUP,
            EvidenceSensitivity.HARD_FACT,
        ),
        (
            "南山好玩吗",
            [],
            {
                "needs_clarification": True,
                "missing_slots": ["place_reference"],
                "entities": SemanticEntities(country="China", city=None, places=[]),
            },
            PrimaryIntent.CLARIFICATION,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
        ),
    ],
)
def test_intent_profile_derivation(
    query,
    needs,
    kwargs,
    expected_intent,
    expected_sensitivity,
):
    frame = _frame(raw_query=query, normalized_request=query, information_needs=needs, **kwargs)
    profile = IntentProfileDeriver().derive(frame)
    assert profile is not None
    assert profile.primary_intent == expected_intent
    assert profile.evidence_sensitivity == expected_sensitivity


def test_lookup_contract_boosts_official_tools():
    frame = _frame(
        raw_query="束河古镇要门票吗",
        information_needs=["ticket_price"],
        decision_type=DecisionType.FACT_LOOKUP,
        task_family=TaskFamily.FACT_LOOKUP,
        requires_exact_fact=True,
    )
    profile = IntentProfileDeriver().derive(frame)
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    assert contract.tool_strategy.initial_tools[:2] == [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
    ]
    assert contract.composition_policy.answer_style == "direct"


def test_comparison_s5_domain_plan_metadata():
    frame = _frame(
        raw_query="束河 vs 白沙",
        information_needs=["value_for_money"],
        decision_type=DecisionType.HOW_TO_CHOOSE,
        task_family=TaskFamily.COMPARISON,
        entities=SemanticEntities(country="China", city="丽江", places=["束河古镇", "白沙古镇"]),
    )
    profile = IntentProfileDeriver().derive(frame)
    strategy = resolve_intent_strategy(profile)
    plan = S5DomainPlanner().plan(None, frame, intent_profile=profile, intent_strategy=strategy)
    assert plan.retrieval_mode == "multi_place_parallel"
    assert plan.intent_primary == PrimaryIntent.COMPARISON
    assert any("comparison parallel" in n for n in plan.notes)
    assert plan.domains[0] == InformationDomain.GEO_RESOLUTION or InformationDomain.REVIEW_SIGNAL in plan.domains


def test_clarification_contract_should_ask():
    frame = _frame(
        raw_query="南山好玩吗",
        needs_clarification=True,
        missing_slots=["place_reference"],
        entities=SemanticEntities(country="China", city=None, places=[]),
    )
    profile = IntentProfileDeriver().derive(frame)
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    assert contract.clarification_policy.should_ask is True
    assert profile.answer_style == AnswerStyle.CLARIFICATION


def test_resolve_compose_mode_from_intent_strategy():
    frame = _frame(
        raw_query="束河 vs 白沙",
        information_needs=["value_for_money"],
        task_family=TaskFamily.COMPARISON,
        decision_type=DecisionType.HOW_TO_CHOOSE,
        entities=SemanticEntities(country="China", city="丽江", places=["束河古镇", "白沙古镇"]),
    )
    state = TravelAgentState(
        session_id="test-session",
        query_id="test-query",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
    )
    state.intent_profile = IntentProfileDeriver().derive(frame)
    state.intent_strategy = resolve_intent_strategy(state.intent_profile)
    mode = TravelAgentStateMachine._resolve_compose_mode(state)
    assert mode == "compare"
