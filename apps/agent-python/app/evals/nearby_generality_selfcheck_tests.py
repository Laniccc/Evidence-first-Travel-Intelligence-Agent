"""Five-direction self-check: nearby task class must work for food/toilet/hotel/parking/station."""

from __future__ import annotations

import pytest

from app.orchestrator.information_need_aliases import (
    infer_nearby_need_from_text,
    is_nearby_need,
    normalize_information_needs,
    primary_nearby_need_from_state,
    resolve_nearby_need,
)
from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.nearby_recommendation_policy import (
    baidu_tag_for_need,
    is_adoptable_nearby_poi,
    nearby_query_suffix_for_need,
)
from app.orchestrator.nearby_task_orchestration import is_nearby_recommendation_task
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.orchestrator.s5_diversified_tool_selector import CLAIM_SEQUENCE_OVERRIDE
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState

# (query, raw_information_needs, expected_canonical_need, expected_baidu_tag, place)
NEARBY_DIRECTIONS = [
    (
        "戏马台附近有什么好吃的？",
        ["nearby_food"],
        "nearby_food",
        "美食",
        "戏马台",
    ),
    (
        "徐州市第三中学附近有没有公共厕所？",
        ["nearby_amenity"],
        "nearby_toilet",
        "生活服务",
        "徐州市第三中学",
    ),
    (
        "徐州市第三中学附近有没有宾馆？",
        ["nearby_accommodation"],
        "nearby_hotel",
        "酒店",
        "徐州市第三中学",
    ),
    (
        "玄武湖公园附近哪里有停车场？",
        ["nearby_parking"],
        "nearby_parking",
        "交通设施",
        "玄武湖公园",
    ),
    (
        "杭州东站附近有公交站吗？",
        ["nearby_station"],
        "nearby_station",
        "交通设施",
        "杭州东站",
    ),
]


def _frame_for(query: str, raw_needs: list[str], place: str) -> SemanticFrame:
    return SemanticFrame(
        raw_query=query,
        normalized_request=query,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.NEARBY_SEARCH,
        entities=SemanticEntities(country="China", city="测试市", places=[place]),
        information_needs=list(raw_needs),
        requires_exact_fact=True,
        confidence=0.85,
    )


def _state_for(query: str, raw_needs: list[str], place: str) -> TravelAgentState:
    frame = _frame_for(query, raw_needs, place)
    profile = IntentProfileDeriver().derive(frame)
    assert profile is not None
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


@pytest.mark.parametrize(
    "query,raw_needs,canonical,tag,place",
    NEARBY_DIRECTIONS,
    ids=["food", "toilet", "hotel", "parking", "station"],
)
def test_nearby_direction_need_resolution(query, raw_needs, canonical, tag, place):
    assert infer_nearby_need_from_text(query) == canonical
    resolved = normalize_information_needs(raw_needs, text=query)
    assert canonical in resolved
    assert is_nearby_need(raw_needs[0])
    assert resolve_nearby_need(raw_needs[0], text=query) == canonical
    assert baidu_tag_for_need(canonical) == tag
    assert nearby_query_suffix_for_need(canonical)


@pytest.mark.parametrize(
    "query,raw_needs,canonical,tag,place",
    NEARBY_DIRECTIONS,
    ids=["food", "toilet", "hotel", "parking", "station"],
)
def test_nearby_direction_intent_and_contract(query, raw_needs, canonical, tag, place):
    state = _state_for(query, raw_needs, place)
    assert state.intent_profile.primary_intent == PrimaryIntent.NEARBY
    claim_types = [c.claim_type for c in state.response_contract.claim_requirements]
    assert canonical in claim_types
    assert primary_nearby_need_from_state(state) == canonical
    assert is_nearby_recommendation_task(state)


@pytest.mark.parametrize(
    "query,raw_needs,canonical,tag,place",
    NEARBY_DIRECTIONS,
    ids=["food", "toilet", "hotel", "parking", "station"],
)
def test_nearby_direction_s5_domain_and_tool_sequence(query, raw_needs, canonical, tag, place):
    state = _state_for(query, raw_needs, place)
    plan = S5DomainPlanner().plan(
        state.response_contract,
        state.semantic_frame,
        intent_profile=state.intent_profile,
        intent_strategy=state.intent_strategy,
    )
    from app.schemas.s5_information_domain import InformationDomain

    assert InformationDomain.NEARBY_RECOMMENDATION in plan.domains
    assert CLAIM_SEQUENCE_OVERRIDE.get(canonical) == "poi_recommendation"


@pytest.mark.parametrize(
    "query,raw_needs,canonical,tag,place",
    NEARBY_DIRECTIONS,
    ids=["food", "toilet", "hotel", "parking", "station"],
)
def test_nearby_retrieval_query_matches_tag(query, raw_needs, canonical, tag, place):
    """Stale query in tool_parameters must not override search_query (regression: 美食 + tag 酒店)."""
    from app.schemas.search_task import SearchTask

    state = _state_for(query, raw_needs, place)
    base = SearchTask(
        task_id="t1",
        search_query="错误残留 美食",
        claim_target="entity_resolution",
        information_need="entity_resolution",
        tool_parameters={"query": f"{place} 美食", "tag": "美食"},
    )
    # Build params the same way as runner (without calling MCP)
    from app.orchestrator.nearby_recommendation_policy import nearby_query_suffix_for_need as suffix_fn

    suffix = suffix_fn(canonical)
    search_query = f"{place} {suffix}".strip()
    base_params = {
        k: v
        for k, v in (base.tool_parameters or {}).items()
        if k not in {"query", "tag", "nearby_search", "latitude", "longitude", "radius"}
    }
    tool_parameters = {**base_params, "query": search_query, "tag": tag}
    assert "美食" not in tool_parameters["query"] or canonical == "nearby_food"
    assert tag in tool_parameters["query"] or suffix in tool_parameters["query"]
    assert tool_parameters["tag"] == tag


def test_hotel_filter_rejects_school_keeps_hotel():
    assert not is_adoptable_nearby_poi(
        "徐州市第三中学(民主校区)",
        "nearby_hotel",
        anchor_place="徐州市第三中学",
    )
    assert is_adoptable_nearby_poi("如家酒店(民主路店)", "nearby_hotel")


def test_toilet_filter_accepts_restroom():
    assert is_adoptable_nearby_poi("民主北路公厕", "nearby_toilet")
    assert not is_adoptable_nearby_poi("郭际辣饼铺", "nearby_toilet")


NEW_CATEGORY_DIRECTIONS = [
    ("玄武湖公园附近有药店吗？", "nearby_pharmacy", "医疗"),
    ("杭州东站附近有没有医院？", "nearby_hospital", "医疗"),
    ("西湖附近有取款机吗？", "nearby_atm", "金融"),
    ("沪宁高速附近有加油站吗？", "nearby_gas", "交通设施"),
    ("奥体中心附近有充电桩吗？", "nearby_charging", "交通设施"),
]


@pytest.mark.parametrize("query,canonical,tag", NEW_CATEGORY_DIRECTIONS)
def test_new_category_inference_and_tags(query, canonical, tag):
    from app.orchestrator.information_need_aliases import infer_all_nearby_needs_from_text

    assert infer_nearby_need_from_text(query) == canonical
    assert infer_all_nearby_needs_from_text(query) == [canonical]
    assert baidu_tag_for_need(canonical) == tag
    assert nearby_query_suffix_for_need(canonical)


def test_compound_food_and_parking_needs():
    from app.orchestrator.information_need_aliases import infer_all_nearby_needs_from_text
    from app.orchestrator.nearby_guided_composition import collect_area_nearby_clues_by_need
    from app.schemas.evidence import Claim, ClaimType, Evidence

    query = "徐州市第三中学附近好吃的和停车场"
    needs = infer_all_nearby_needs_from_text(query)
    assert "nearby_food" in needs
    assert "nearby_parking" in needs
    assert len(needs) == 2

    frame = _frame_for(query, ["nearby_food"], "徐州市第三中学")
    state = _state_for(query, ["nearby_food"], "徐州市第三中学")
    state.evidence = [
        Evidence(
            evidence_id="ev-food",
            source_name="Baidu Maps MCP",
            source_type="map",
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.FOOD,
                    value="辣饼铺（中学街）",
                    normalized_value={"information_need": "nearby_food", "search_tag": "美食"},
                    confidence=0.7,
                )
            ],
            confidence=0.7,
        ),
        Evidence(
            evidence_id="ev-park",
            source_name="Baidu Maps MCP",
            source_type="map",
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.GENERAL_FACT,
                    value="民主北路停车场（民主北路）",
                    normalized_value={
                        "information_need": "nearby_parking",
                        "search_tag": "停车场",
                        "baidu_item_tag": "停车场",
                    },
                    confidence=0.7,
                )
            ],
            confidence=0.7,
        ),
    ]
    by_need = collect_area_nearby_clues_by_need(state)
    assert len(by_need.get("nearby_food") or []) >= 1
    assert len(by_need.get("nearby_parking") or []) >= 1


def test_compound_query_contract_has_multiple_claims():
    query = "戏马台附近好吃的和停车场"
    frame = _frame_for(query, ["nearby_food"], "戏马台")
    profile = IntentProfileDeriver().derive(frame)
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    nearby_claims = [c.claim_type for c in contract.claim_requirements if c.claim_type.startswith("nearby_")]
    assert "nearby_food" in nearby_claims
    assert "nearby_parking" in nearby_claims


def test_hotel_tag_only_adoption():
    assert is_adoptable_nearby_poi(
        "全季徐州民主路店",
        "nearby_hotel",
        poi_tag="酒店",
        search_tag="酒店",
    )
    assert not is_adoptable_nearby_poi(
        "徐州市第三中学(民主校区)",
        "nearby_hotel",
        poi_tag="教育培训",
        search_tag="酒店",
        anchor_place="徐州市第三中学",
    )
