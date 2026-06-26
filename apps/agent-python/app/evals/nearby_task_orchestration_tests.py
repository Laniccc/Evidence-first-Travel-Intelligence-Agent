"""Tests for nearby task-class orchestration and guided composition."""

from __future__ import annotations

from app.orchestrator.nearby_guided_composition import (
    build_nearby_guided_draft,
    collect_area_nearby_clues,
)
from app.orchestrator.nearby_task_orchestration import (
    count_nearby_actionable_claims,
    count_nearby_food_claims,
    is_nearby_recommendation_task,
    nearby_s5_may_finish_early,
    resolve_nearby_compose_mode,
    should_use_nearby_guided_compose,
)
from app.orchestrator.information_need_aliases import (
    infer_nearby_need_from_text,
    primary_nearby_need_from_state,
    resolve_nearby_need,
)
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.schemas.evidence import Claim, ClaimType, Evidence
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _nearby_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="戏马台附近有什么好吃的？",
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.NEARBY_SEARCH,
        entities=SemanticEntities(country="China", city="徐州", places=["戏马台"]),
        information_needs=["nearby_food"],
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.NEARBY,
        intent_subtypes=[],
        evidence_sensitivity=EvidenceSensitivity.EVIDENCE_PREFERRED,
        answer_style=AnswerStyle.RECOMMENDATION_LIST,
        confidence=0.8,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def _food_evidence(*names: str) -> Evidence:
    claims = [
        Claim(claim_type=ClaimType.FOOD, value=f"{n}（测试地址）", confidence=0.68)
        for n in names
    ]
    return Evidence(
        evidence_id="ev-food",
        source_name="Baidu Maps MCP",
        source_type="map",
        country="China",
        place_name="户部山戏马台",
        claims=claims,
        confidence=0.68,
    )


def test_is_nearby_recommendation_task():
    state = _nearby_state()
    assert is_nearby_recommendation_task(state)


def test_count_area_nearby_clues():
    state = _nearby_state()
    state.evidence = [
        _food_evidence("老锅台辣汤", "李先生牛肉面", "老徐州地锅鸡"),
        Evidence(
            evidence_id="ev-cand",
            source_name="Baidu Maps MCP",
            source_type="map",
            country="China",
            place_name="户部山戏马台",
            claims=[
                Claim(
                    claim_type=ClaimType.PLACE_CANDIDATES,
                    value=[
                        {"name": "户部山戏马台", "city": "徐州市", "latitude": 34.26, "longitude": 117.19},
                        {"name": "戏马台-北门", "city": "徐州市", "latitude": 34.26, "longitude": 117.19},
                    ],
                    confidence=0.6,
                )
            ],
            confidence=0.62,
        ),
    ]
    assert count_nearby_food_claims(state.evidence) == 3
    clues = collect_area_nearby_clues(state)
    assert len(clues) == 3


def test_should_use_nearby_guided_compose_with_food_and_sub_poi():
    state = _nearby_state()
    state.evidence = [
        _food_evidence("老锅台辣汤"),
        Evidence(
            evidence_id="ev-cand",
            source_name="Baidu Maps MCP",
            source_type="map",
            country="China",
            place_name="户部山戏马台",
            claims=[
                Claim(
                    claim_type=ClaimType.PLACE_CANDIDATES,
                    value=[
                        {
                            "name": "户部山戏马台",
                            "city": "徐州市",
                            "province": "江苏省",
                            "latitude": 34.260959,
                            "longitude": 117.19655,
                        },
                        {
                            "name": "戏马台-北门",
                            "city": "徐州市",
                            "province": "江苏省",
                            "latitude": 34.260127,
                            "longitude": 117.196237,
                        },
                    ],
                    confidence=0.6,
                )
            ],
            confidence=0.62,
        ),
    ]
    assert should_use_nearby_guided_compose(state)
    assert resolve_nearby_compose_mode(state) == "nearby_guided"


def test_nearby_guided_draft_lists_all_area_foods():
    state = _nearby_state()
    state.evidence = [_food_evidence("A店", "B店", "C店")]
    draft = build_nearby_guided_draft(state)
    text = draft.render_text()
    assert "A店" in text and "B店" in text and "C店" in text
    assert "共 3 条" in text or "3 条" in text


def test_nearby_s5_may_finish_after_entity_resolution():
    state = _nearby_state()
    state.evidence = [_food_evidence("A店")]
    state.structured_result = {
        "subagent_results": [{"subagent": "entity_resolution_agent", "evidence_count": 5}]
    }
    assert nearby_s5_may_finish_early(state, step=2)


def _toilet_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="徐州市第三中学附近有没有公共厕所？",
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.NEARBY_SEARCH,
        entities=SemanticEntities(country="China", city="徐州", places=["徐州市第三中学"]),
        information_needs=["nearby_amenity"],
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.NEARBY,
        intent_subtypes=["nearby_amenity"],
        evidence_sensitivity=EvidenceSensitivity.EVIDENCE_PREFERRED,
        answer_style=AnswerStyle.RECOMMENDATION_LIST,
        confidence=0.88,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q2", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def _toilet_evidence(*names: str) -> Evidence:
    claims = [
        Claim(claim_type=ClaimType.GENERAL_FACT, value=f"{n} — 测试路1号", confidence=0.65)
        for n in names
    ]
    return Evidence(
        evidence_id="ev-toilet",
        source_name="Baidu Maps MCP",
        source_type="map",
        country="China",
        place_name="徐州市第三中学",
        claims=claims,
        confidence=0.65,
    )


def test_nearby_amenity_resolves_to_toilet_from_text():
    assert infer_nearby_need_from_text("徐州市第三中学附近有没有公共厕所？") == "nearby_toilet"
    assert resolve_nearby_need("nearby_amenity", text="附近公共厕所") == "nearby_toilet"


def test_toilet_contract_not_nearby_food():
    state = _toilet_state()
    claim_types = [c.claim_type for c in state.response_contract.claim_requirements]
    assert "nearby_food" not in claim_types
    assert "nearby_toilet" in claim_types
    assert primary_nearby_need_from_state(state) == "nearby_toilet"


def test_toilet_guided_draft_uses_toilet_wording_not_food():
    state = _toilet_state()
    state.evidence = [_toilet_evidence("民主北路公厕", "汇金广场卫生间")]
    draft = build_nearby_guided_draft(state)
    text = draft.render_text()
    assert "民主北路公厕" in text
    assert "老八羊肉" not in text
    assert "美食" not in text or "周边厕所" in text
    assert "公厕" in text or "厕所" in text


def test_count_nearby_actionable_claims_for_toilet():
    ev = _toilet_evidence("A公厕", "B卫生间")
    assert count_nearby_actionable_claims([ev], "nearby_toilet") == 2
    assert count_nearby_actionable_claims([ev], "nearby_food") == 0


def _hotel_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="徐州市第三中学附近有没有宾馆？",
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.NEARBY_SEARCH,
        entities=SemanticEntities(country="China", city="徐州", places=["徐州市第三中学"]),
        information_needs=["nearby_accommodation"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.NEARBY,
        intent_subtypes=["nearby_accommodation"],
        evidence_sensitivity=EvidenceSensitivity.EVIDENCE_PREFERRED,
        answer_style=AnswerStyle.RECOMMENDATION_LIST,
        confidence=0.85,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q3", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def test_hotel_contract_and_intent_not_food():
    from app.orchestrator.intent_profile_deriver import IntentProfileDeriver

    state = _hotel_state()
    claim_types = [c.claim_type for c in state.response_contract.claim_requirements]
    assert "nearby_hotel" in claim_types
    assert "nearby_food" not in claim_types
    profile = IntentProfileDeriver().derive(state.semantic_frame)
    assert profile.primary_intent == PrimaryIntent.NEARBY


def test_hotel_guided_draft_excludes_school_and_food():
    state = _hotel_state()
    state.evidence = [
        Evidence(
            evidence_id="ev-mix",
            source_name="Baidu Maps MCP",
            source_type="map",
            country="China",
            place_name="徐州市第三中学",
            claims=[
                Claim(claim_type=ClaimType.LODGING, value="徐州市第三中学(民主校区)（民主北路47号）", confidence=0.68),
                Claim(claim_type=ClaimType.LODGING, value="郭际辣饼铺(第三中学店)（中学街）", confidence=0.68),
                Claim(claim_type=ClaimType.LODGING, value="如家酒店(民主路店)（民主北路100号）", confidence=0.68),
            ],
            confidence=0.68,
        )
    ]
    clues = collect_area_nearby_clues(state)
    texts = " ".join(c["text"] for c in clues)
    assert "如家" in texts
    assert "辣饼" not in texts
    assert "民主校区）" not in texts or "如家" in texts
