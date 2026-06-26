"""S5 diversified tool selector and attempt ledger tests."""

from __future__ import annotations

import pytest

from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_diversified_tool_selector import (
    S5DiversifiedToolSelector,
    untried_must_attempt_tools,
)
from app.orchestrator.s5_tool_attempt_ledger import record_tool_attempt
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.search_task import SearchTask
from app.schemas.semantic_frame import (
    DecisionType,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.user_query import TravelAgentState


def _nearby_food_state(query: str, place: str) -> TravelAgentState:
    frame = SemanticFrame(
        raw_query=query,
        normalized_request=query,
        information_needs=["restaurant_recommendation", "nearby_places", "reputation"],
        decision_type=DecisionType.NEARBY_SEARCH,
        task_family=TaskFamily.ADVISORY,
        entities=SemanticEntities(country="China", city="徐州", places=[place]),
        time_scope=TimeScope.FLEXIBLE,
        can_answer_with_model_prior=False,
    )
    profile = IntentProfileDeriver().derive(frame)
    assert profile is not None
    assert profile.primary_intent == PrimaryIntent.NEARBY
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    strategy = resolve_intent_strategy(profile)
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=query,
        semantic_frame=frame,
        response_contract=contract,
        intent_profile=profile,
        intent_strategy=strategy,
    )


def test_nearby_food_first_tool_is_baidu_place_search_not_search_mcp():
    state = _nearby_food_state("戏马台附近有什么好吃的？", "戏马台")
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    selector = S5DiversifiedToolSelector(state)
    sel = selector.select_next("nearby_food", wl, subagent="fact_search_agent")
    assert sel is not None
    assert sel.tool_name == "baidu_place_search_mcp"
    assert sel.tier == "must_attempt"


def test_rotation_skips_repeated_search_mcp_after_two_attempts():
    state = _nearby_food_state("戏马台附近有什么好吃的？", "戏马台")
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    record_tool_attempt(
        state,
        tool_name="search_mcp",
        claim_type="nearby_food",
        subagent="fact_search_agent",
        status="zero_evidence",
    )
    record_tool_attempt(
        state,
        tool_name="search_mcp",
        claim_type="nearby_food",
        subagent="fact_search_agent",
        status="zero_evidence",
    )
    selector = S5DiversifiedToolSelector(state)
    sel = selector.select_next("nearby_food", wl, subagent="fact_search_agent")
    assert sel is not None
    assert sel.tool_name != "search_mcp"
    assert sel.tool_name == "baidu_place_search_mcp"


def test_must_attempt_remaining_excludes_optional_only_tools():
    state = _nearby_food_state("束河古镇附近有什么餐厅", "束河古镇")
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    remaining = untried_must_attempt_tools(state, wl)
    assert "baidu_place_search_mcp" in remaining
    record_tool_attempt(
        state,
        tool_name="baidu_place_search_mcp",
        claim_type="nearby_food",
        subagent="fact_search_agent",
        status="ok",
        evidence_count=3,
    )
    remaining_after = untried_must_attempt_tools(state, wl)
    assert "baidu_place_search_mcp" not in remaining_after


def test_validate_skips_baidu_place_detail_without_uid():
    state = _nearby_food_state("戏马台附近美食", "戏马台")
    selector = S5DiversifiedToolSelector(state)
    assert selector.validate_tool_args("baidu_place_detail_mcp", claim_type="nearby_food") is False


def test_fact_search_task_ignores_search_mcp_preferred_override():
    state = _nearby_food_state("戏马台附近有什么好吃的？", "戏马台")
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    task = SearchTask(
        task_id="t1",
        lookup_intent="nearby food",
        claim_target="nearby_food",
        information_need="nearby_food",
        search_query="戏马台 美食",
        preferred_tool="search_mcp",
    )
    from app.orchestrator.s5_diversified_tool_selector import select_tool_for_subagent

    sel = select_tool_for_subagent(state, task, wl, subagent="fact_search_agent")
    assert sel is not None
    assert sel.tool_name == "baidu_place_search_mcp"
    assert sel.skip_preferred_override is True


def test_non_search_queue_prioritizes_poi_tools():
    state = _nearby_food_state("戏马台附近有什么好吃的？", "戏马台")
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    queue = S5DiversifiedToolSelector(state).non_search_tool_queue(wl, claim_type="nearby_food")
    assert queue
    assert queue[0] == "baidu_place_search_mcp"
    assert "search_mcp" not in queue
