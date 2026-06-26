"""Tests for nearby POI reputation enrichment policy and S8 merge."""

from __future__ import annotations

from app.orchestrator.nearby_enrichment_policy import (
    build_poi_reputation_index,
    count_pois_with_reputation,
    enrichment_candidates_from_evidence,
    lookup_poi_reputation,
    requires_nearby_reputation_signal,
)
from app.orchestrator.nearby_guided_composition import collect_area_nearby_clues
from app.orchestrator.nearby_category_registry import enrichment_enabled_for_category, enrichment_top_n_for_category
from app.orchestrator.nearby_task_orchestration import nearby_s5_skip_fact_search
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.schemas.evidence import Claim, ClaimType, Evidence
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _food_state(*, query: str, needs: list[str]) -> TravelAgentState:
    frame = SemanticFrame(
        raw_query=query,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.NEARBY_SEARCH,
        entities=SemanticEntities(country="China", city="徐州", places=["戏马台"]),
        information_needs=needs,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.NEARBY,
        intent_subtypes=[],
        evidence_sensitivity=EvidenceSensitivity.EVIDENCE_PREFERRED,
        answer_style=AnswerStyle.RECOMMENDATION_LIST,
        confidence=0.8,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=query)
    state.semantic_frame = frame
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def _nearby_food_claim(name: str, *, uid: str) -> Claim:
    return Claim(
        claim_type=ClaimType.FOOD,
        value=f"{name}（测试路1号）",
        normalized_value={
            "uid": uid,
            "name": name,
            "retrieval_context": "nearby_recommendation",
            "information_need": "nearby_food",
        },
        confidence=0.68,
    )


def test_food_taxonomy_enrichment_config():
    assert enrichment_enabled_for_category("nearby_food")
    assert enrichment_top_n_for_category("nearby_food") == 5


def test_requires_reputation_from_user_text():
    state = _food_state(query="戏马台附近口碑好的餐厅", needs=["nearby_food"])
    assert requires_nearby_reputation_signal(state)


def test_enrichment_candidates_dedupe_by_uid():
    ev = Evidence(
        evidence_id="e1",
        source_name="Baidu",
        source_type="map",
        country="China",
        claims=[
            _nearby_food_claim("A店", uid="u1"),
            _nearby_food_claim("A店分店", uid="u1"),
            _nearby_food_claim("B店", uid="u2"),
        ],
        confidence=0.7,
    )
    rows = enrichment_candidates_from_evidence([ev], "nearby_food", limit=5)
    assert len(rows) == 2
    assert rows[0]["uid"] == "u1"


def test_reputation_index_and_clue_merge():
    state = _food_state(query="戏马台附近美食", needs=["nearby_food"])
    state.evidence = [
        Evidence(
            evidence_id="e1",
            source_name="Baidu",
            source_type="map",
            country="China",
            claims=[_nearby_food_claim("老锅台", uid="u1"), _nearby_food_claim("李先生", uid="u2")],
            confidence=0.7,
        ),
        Evidence(
            evidence_id="e2",
            source_name="Baidu Maps MCP",
            source_type="map",
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.RATING_CANDIDATE,
                    value="4.6",
                    normalized_value={
                        "rating": "4.6",
                        "review_count": 128,
                        "poi_uid": "u1",
                        "poi_name": "老锅台",
                    },
                    confidence=0.6,
                )
            ],
            confidence=0.6,
        ),
        Evidence(
            evidence_id="e3",
            source_name="Dianping",
            source_type="review_platform",
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.REVIEW_SUMMARY,
                    value="辣汤很地道，早点人多要排队",
                    normalized_value={"poi_uid": "u2", "poi_name": "李先生"},
                    confidence=0.55,
                )
            ],
            confidence=0.55,
        ),
    ]
    index = build_poi_reputation_index(state.evidence)
    assert lookup_poi_reputation(index, uid="u1")["rating"] == "4.6"
    clues = collect_area_nearby_clues(state)
    texts = " ".join(c["text"] for c in clues)
    assert "评分 4.6" in texts
    assert "128条评价" in texts
    assert "辣汤很地道" in texts


def test_reputation_satisfied_counts_top_pois():
    ev = [
        Evidence(
            evidence_id="e1",
            source_name="Baidu",
            source_type="map",
            country="China",
            claims=[
                _nearby_food_claim("A", uid="u1"),
                _nearby_food_claim("B", uid="u2"),
            ],
            confidence=0.7,
        ),
        Evidence(
            evidence_id="e2",
            source_name="Baidu",
            source_type="map",
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.RATING_CANDIDATE,
                    value="4.5",
                    normalized_value={"rating": "4.5", "poi_uid": "u1", "poi_name": "A"},
                    confidence=0.6,
                ),
                Claim(
                    claim_type=ClaimType.REVIEW_SUMMARY,
                    value="不错",
                    normalized_value={"poi_uid": "u2", "poi_name": "B"},
                    confidence=0.5,
                ),
            ],
            confidence=0.6,
        ),
    ]
    assert count_pois_with_reputation(ev, "nearby_food", top_n=2) == 2


def test_skip_fact_search_false_when_reputation_required_but_missing():
    state = _food_state(query="戏马台附近口碑好的美食", needs=["nearby_food", "review_summary"])
    state.evidence = [
        Evidence(
            evidence_id="e1",
            source_name="Baidu",
            source_type="map",
            country="China",
            claims=[
                _nearby_food_claim("A", uid="u1"),
                _nearby_food_claim("B", uid="u2"),
                _nearby_food_claim("C", uid="u3"),
            ],
            confidence=0.7,
        )
    ]
    assert nearby_s5_skip_fact_search(state) is False
