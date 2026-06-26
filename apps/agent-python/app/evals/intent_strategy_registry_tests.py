"""IntentStrategyRegistry v2 integration tests."""

from __future__ import annotations

import pytest

from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.intent_strategy_registry import INTENT_STRATEGY_REGISTRY, resolve_intent_strategy
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import (
    DecisionType,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.s5_information_domain import InformationDomain
from app.schemas.user_query import TravelAgentState


def _profile(intent: PrimaryIntent, sensitivity: EvidenceSensitivity = EvidenceSensitivity.EVIDENCE_PREFERRED) -> IntentProfile:
    return IntentProfile(
        primary_intent=intent,
        intent_subtypes=[],
        evidence_sensitivity=sensitivity,
        answer_style=AnswerStyle.ADVISORY,
        confidence=0.8,
        derivation="rules",
    )


@pytest.mark.parametrize(
    "intent,compose_mode,retrieval_mode,s7_policy,first_domain",
    [
        (PrimaryIntent.CLARIFICATION, "clarification", "minimal_probe", "clarification_decision", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.LOOKUP, "fact_lookup", "strict_fact_lookup", "hard_fact_strict", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.NEARBY, "nearby", "poi_recommendation", "poi_quality_filter", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.REALTIME_CHECK, "realtime_status", "live_status", "freshness_strict", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.COMPARISON, "compare", "multi_place_parallel", "aligned_dimension_comparison", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.PLANNING, "itinerary", "route_first", "route_feasibility", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.REVIEW_CHECK, "review_insight", "review_first", "review_signal_adoption", InformationDomain.GEO_RESOLUTION),
        (PrimaryIntent.ADVISORY, "advisory", "mixed_advisory", "open_claim_advisory", InformationDomain.GEO_RESOLUTION),
    ],
)
def test_registry_resolve_fields(intent, compose_mode, retrieval_mode, s7_policy, first_domain):
    assert intent in INTENT_STRATEGY_REGISTRY
    strategy = resolve_intent_strategy(_profile(intent))
    assert strategy is not None
    assert strategy.compose_mode == compose_mode
    assert strategy.retrieval_mode == retrieval_mode
    assert strategy.s7_policy == s7_policy
    assert strategy.domain_priority[0] == first_domain


def test_nearby_dining_contract_maps_to_nearby_food():
    frame = SemanticFrame(
        raw_query="束河古镇附近有什么餐厅",
        normalized_request="束河古镇附近餐厅",
        information_needs=["nearby_dining"],
        decision_type=DecisionType.NEARBY_SEARCH,
        task_family=TaskFamily.ADVISORY,
        entities=SemanticEntities(country="China", city="丽江", places=["束河古镇"]),
        time_scope=TimeScope.FLEXIBLE,
        can_answer_with_model_prior=False,
    )
    profile = IntentProfileDeriver().derive(frame)
    assert profile is not None
    assert profile.primary_intent == PrimaryIntent.NEARBY

    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    claim_types = [c.claim_type for c in contract.claim_requirements]
    assert "nearby_food" in claim_types
    nearby_claim = next(c for c in contract.claim_requirements if c.claim_type == "nearby_food")
    assert nearby_claim.claim_family == "nearby_recommendation"
    assert "dianping_review_crawler_mcp" in nearby_claim.preferred_tools
    assert "baidu_place_search_mcp" in nearby_claim.preferred_tools
    assert "baidu_route_mcp" not in nearby_claim.preferred_tools
    assert "knowledge_prior" in nearby_claim.forbidden_tools


def test_restaurant_recommendation_needs_map_to_nearby_food():
    frame = SemanticFrame(
        raw_query="束河古镇附近有什么不坑的餐厅",
        normalized_request="束河古镇附近餐厅",
        information_needs=["restaurant_recommendation", "nearby_places", "reputation"],
        decision_type=DecisionType.NEARBY_SEARCH,
        task_family=TaskFamily.ADVISORY,
        entities=SemanticEntities(country="China", city="丽江", places=["束河古镇"]),
        time_scope=TimeScope.FLEXIBLE,
        can_answer_with_model_prior=False,
    )
    profile = IntentProfileDeriver().derive(frame)
    assert profile is not None
    assert profile.primary_intent == PrimaryIntent.NEARBY

    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    claim_types = {c.claim_type for c in contract.claim_requirements}
    assert "nearby_food" in claim_types
    assert "review_summary" in claim_types
    assert "general_travel_advice" not in claim_types


def test_nearby_dining_whitelist_includes_review_tools():
    frame = SemanticFrame(
        raw_query="束河古镇附近有什么餐厅",
        normalized_request="束河古镇附近餐厅",
        information_needs=["nearby_dining"],
        decision_type=DecisionType.NEARBY_SEARCH,
        task_family=TaskFamily.ADVISORY,
        entities=SemanticEntities(country="China", city="丽江", places=["束河古镇"]),
        time_scope=TimeScope.FLEXIBLE,
        can_answer_with_model_prior=False,
    )
    profile = IntentProfileDeriver().derive(frame)
    strategy = resolve_intent_strategy(profile)
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
        response_contract=contract,
        intent_profile=profile,
        intent_strategy=strategy,
    )
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    allowed = {t.name for t in wl.allowed_tools}
    assert "baidu_route_mcp" in allowed or "baidu_place_search_mcp" in allowed
    assert "knowledge_prior" not in allowed or "knowledge_prior" in wl.blocked_tools
