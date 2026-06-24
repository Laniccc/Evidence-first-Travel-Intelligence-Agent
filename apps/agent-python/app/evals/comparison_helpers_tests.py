"""Comparison retrieval helpers and contract tests."""

from __future__ import annotations

from app.orchestrator.comparison_helpers import (
    build_comparison_search_query,
    disambiguated_place_label,
    is_homonym_polluted,
)
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    IntentProfile,
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
def _frame(**kwargs) -> SemanticFrame:
    base = dict(
        raw_query="禾木和喀纳斯只能选一个去哪？",
        normalized_request="禾木和喀纳斯只能选一个去哪？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.COMPARISON,
        decision_type=DecisionType.HOW_TO_CHOOSE,
        entities=SemanticEntities(
            country="China",
            city="Altay",
            region="新疆",
            places=["禾木村", "喀纳斯景区"],
        ),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=["crowd_level", "transit"],
    )
    base.update(kwargs)
    return SemanticFrame(**base)


def test_places_match_fuzzy_aliases():
    from app.orchestrator.comparison_helpers import places_match

    assert places_match("禾木村", "禾木") is True
    assert places_match("喀纳斯景区", "喀纳斯") is True
    assert places_match("禾木村", "喀纳斯景区") is False


def test_summarize_comparison_claims_fuzzy_place_labels():
    from app.orchestrator.comparison_helpers import summarize_comparison_claims_for_compose

    claims = [
        {
            "place_name": "禾木",
            "claim_type": "review_summary",
            "value": "秋色很美",
            "confidence": 0.8,
            "relevance_score": 0.9,
            "evidence_id": "e1",
        },
        {
            "place_name": "喀纳斯",
            "claim_type": "crowd_level",
            "value": "旺季游客较多",
            "confidence": 0.7,
            "relevance_score": 0.8,
            "evidence_id": "e2",
        },
    ]
    out = summarize_comparison_claims_for_compose(claims, ["禾木村", "喀纳斯景区"])
    assert len(out) == 2
    place_names = {c["place_name"] for c in out}
    assert "禾木" in place_names
    assert "喀纳斯" in place_names


def test_disambiguated_place_label_includes_region_city():
    label = disambiguated_place_label("禾木村", city="Altay", region="新疆", country="China")
    assert "禾木村" in label
    assert "新疆" in label or "Altay" in label


def test_build_comparison_search_query_not_single_char():
    frame = _frame()
    query = build_comparison_search_query(
        "禾木村",
        "crowd_level",
        frame,
        peer_places=["喀纳斯景区"],
        user_query=frame.raw_query,
    )
    assert "禾木村" in query
    assert "禾" != query.strip()
    assert len(query) > 6


def test_homonym_pollution_filters_he_character_baike():
    ev = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        country="China",
        source_url="https://baike.baidu.com/item/%E7%A6%BE/4864824",
        place_name="禾木村",
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value="禾（汉语文字）_百度百科: 有时专指稻子。禾是汉字部首之一",
            )
        ],
    )
    assert is_homonym_polluted(ev, "禾木村") is True


def test_comparison_contract_includes_crowd_transit_review():
    frame = _frame()
    profile = IntentProfile(
        primary_intent=PrimaryIntent.COMPARISON,
        evidence_sensitivity=EvidenceSensitivity.EVIDENCE_PREFERRED,
        answer_style=AnswerStyle.COMPARISON,
    )
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    types = {c.claim_type for c in contract.claim_requirements}
    assert "crowd_level" in types
    assert "route_plan" in types
    assert "review_summary" in types
    assert "general_travel_advice" not in types
    assert contract.tool_strategy.max_tool_steps >= 14


def test_curate_comparison_claim_rows_per_place():
    from app.orchestrator.comparison_helpers import curate_comparison_claim_rows

    places = ["禾木村", "喀纳斯景区"]
    evidence = [
        Evidence(
            source_name="ctrip",
            source_type=SourceType.WEB,
            country="China",
            place_name="禾木村",
            claims=[
                Claim(claim_type=ClaimType.REVIEW_SUMMARY, value="禾木村秋色很美，游客较多"),
            ],
        ),
        Evidence(
            source_name="search",
            source_type=SourceType.WEB,
            country="China",
            place_name="喀纳斯景区",
            claims=[
                Claim(claim_type=ClaimType.TRAVEL_ADVICE, value="喀纳斯景区交通需自驾，风景值得"),
            ],
        ),
    ]
    rows = curate_comparison_claim_rows(evidence, places)
    assert len(rows) >= 2
    place_names = {r.place_name for r in rows}
    assert "禾木村" in place_names
    assert "喀纳斯景区" in place_names
