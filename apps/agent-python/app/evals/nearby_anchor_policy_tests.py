"""Nearby anchor strategy: per-candidate vs fuzzy search planning."""

from __future__ import annotations

from app.orchestrator.nearby_anchor_policy import (
    build_nearby_search_targets,
    same_scenic_area_sub_poi_ambiguity,
)
from app.orchestrator.s5_task_tool_catalogs.resolver import catalog_entry
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _ximatai_candidates() -> list[dict]:
    return [
        {
            "name": "户部山戏马台",
            "city": "徐州市",
            "province": "江苏省",
            "latitude": 34.260959,
            "longitude": 117.196550,
        },
        {
            "name": "户部山戏马台-地上停车场",
            "city": "徐州市",
            "latitude": 34.260127,
            "longitude": 117.196237,
        },
        {
            "name": "戏马台-北门",
            "city": "徐州市",
            "latitude": 34.260127,
            "longitude": 117.196237,
        },
    ]


def test_same_scenic_area_sub_poi_ambiguity_for_ximatai():
    assert same_scenic_area_sub_poi_ambiguity(_ximatai_candidates(), "戏马台")


def test_build_targets_per_candidate_for_disambiguation():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="戏马台附近有什么好吃的？",
        semantic_frame=SemanticFrame(
            raw_query="戏马台附近有什么好吃的？",
            task_family=TaskFamily.ADVISORY,
            entities=SemanticEntities(country="China", city="徐州", places=["戏马台"]),
            information_needs=["nearby_food"],
        ),
    )
    plan = build_nearby_search_targets(
        state,
        _ximatai_candidates(),
        nearby_claim="nearby_food",
    )
    assert plan["per_candidate"] is True
    assert plan["search_mode"] == "per_candidate_precise"
    assert len(plan["search_targets"]) == 3
    assert all(t.get("coordinates") for t in plan["search_targets"])


def test_poi_recommendation_catalog_differs_from_shared_for_dianping():
    shared = catalog_entry("dianping_nearby_crawler_mcp")
    poi = catalog_entry("dianping_nearby_crawler_mcp", task_class="poi_recommendation")
    assert shared is not None and poi is not None
    poi_joined = " ".join(poi.when_to_use)
    assert "美食" in poi_joined
    assert poi.summary != shared.summary or poi.when_to_use != shared.when_to_use
