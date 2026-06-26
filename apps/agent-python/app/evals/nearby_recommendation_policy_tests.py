"""Nearby recommendation policy: S5 claims, S7 scoring, S8 presentation."""

from __future__ import annotations

from app.orchestrator.claim_policy_registry import resolve_policy
from app.orchestrator.evidence_scorer import EvidenceScorer
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.response_contract import ClaimRequirement
from tools.mcp.adapters.baidu_response_parser import search_claims


def _restaurant_candidates() -> list[dict]:
    return [
        {
            "name": "箸福·夜上海(玄武湖名湖美景店)",
            "uid": "44427df4722600b0c4f50da8",
            "city": "南京市",
            "province": "江苏省",
            "address": "龙蟠路88号国展中心北门2-4楼",
            "latitude": 32.08167095944563,
            "longitude": 118.81451578798779,
        },
        {
            "name": "好记·翰景轩·书画餐厅(玄武湖店)",
            "uid": "f2f3552cef8879e480a00c10",
            "city": "南京市",
            "province": "江苏省",
            "address": "西家大塘46-3号玄武门",
            "latitude": 32.08189671147555,
            "longitude": 118.81441956403478,
        },
    ]


def test_nearby_food_search_claims_emit_food_and_tagged_place_candidates():
    claims = search_claims(
        _restaurant_candidates(),
        information_need="nearby_food",
        nearby_search=True,
        tag="美食",
        latitude=32.07,
    )
    types = {c.claim_type for c in claims}
    assert ClaimType.FOOD in types
    assert ClaimType.PLACE_CANDIDATES in types
    pc = next(c for c in claims if c.claim_type == ClaimType.PLACE_CANDIDATES)
    assert pc.normalized_value.get("retrieval_context") == "nearby_recommendation"
    assert pc.normalized_value.get("information_need") == "nearby_food"


def test_nearby_toilet_search_claims_emit_general_fact():
    claims = search_claims(
        [{"name": "玄武湖公园公厕", "address": "南京市玄武区玄武巷1号", "latitude": 32.07, "longitude": 118.8}],
        information_need="nearby_toilet",
        nearby_search=True,
        tag="厕所",
        latitude=32.07,
    )
    types = {c.claim_type for c in claims}
    assert ClaimType.GENERAL_FACT in types
    assert ClaimType.FOOD not in types


def test_entity_resolution_search_does_not_emit_food_claims():
    claims = search_claims(
        [{"name": "玄武湖景区", "uid": "u1", "latitude": 32.07, "longitude": 118.8}],
        information_need="entity_resolution",
    )
    types = {c.claim_type for c in claims}
    assert ClaimType.FOOD not in types


def test_s7_scores_nearby_food_from_map_food_claims():
    claims = search_claims(
        _restaurant_candidates(),
        information_need="nearby_food",
        nearby_search=True,
        tag="美食",
        latitude=32.07,
    )
    ev = Evidence(
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        city="南京",
        place_name="箸福·夜上海(玄武湖名湖美景店)",
        claims=claims,
    )
    policy = resolve_policy(
        ClaimRequirement(claim_type="nearby_food", priority="required", claim_family="nearby_recommendation")
    )
    scores = EvidenceScorer().score_claim_evidence(policy, [ev])
    assert scores
    assert any(s.claim_value and "箸福" in s.claim_value for s in scores)


def test_s8_focus_maps_nearby_food_to_food_claim_type():
    from app.orchestrator.nearby_recommendation_policy import s8_focus_claim_types

    focus = s8_focus_claim_types("nearby_food")
    assert "food" in focus
    assert "nearby_food" not in focus


def test_nearby_hotel_filters_school_and_food_pois():
    claims = search_claims(
        [
            {"name": "徐州市第三中学(民主校区)", "address": "民主北路47号"},
            {"name": "郭际辣饼铺(第三中学店)", "address": "中学街"},
            {"name": "如家酒店(徐州民主路店)", "address": "民主北路"},
        ],
        information_need="nearby_hotel",
        nearby_search=True,
        tag="酒店",
        latitude=34.27,
        anchor_candidate_name="徐州市第三中学(民主校区)",
    )
    lodging = [c for c in claims if c.claim_type == ClaimType.LODGING]
    assert len(lodging) == 1
    assert "如家" in str(lodging[0].value)


def test_nearby_accommodation_alias_resolves_to_hotel():
    from app.orchestrator.information_need_aliases import resolve_nearby_need

    assert resolve_nearby_need("nearby_accommodation", text="附近宾馆") == "nearby_hotel"


def test_nearby_hotel_adopts_brand_without_keyword_in_name():
    claims = search_claims(
        [{"name": "全季徐州民主路店", "address": "民主北路", "tag": "酒店"}],
        information_need="nearby_hotel",
        nearby_search=True,
        tag="酒店",
        latitude=34.27,
    )
    lodging = [c for c in claims if c.claim_type == ClaimType.LODGING]
    assert len(lodging) == 1
    assert "全季" in str(lodging[0].value)


def test_nearby_hotel_tag_only_poi_adopted():
    claims = search_claims(
        [{"name": "民主北路店", "address": "民主北路", "tag": "酒店"}],
        information_need="nearby_hotel",
        nearby_search=True,
        tag="酒店",
        latitude=34.27,
    )
    lodging = [c for c in claims if c.claim_type == ClaimType.LODGING]
    assert len(lodging) == 1


def test_nearby_hotel_rejects_conflicting_tag():
    claims = search_claims(
        [{"name": "某小吃店", "address": "中学街", "tag": "美食"}],
        information_need="nearby_hotel",
        nearby_search=True,
        tag="酒店",
        latitude=34.27,
    )
    lodging = [c for c in claims if c.claim_type == ClaimType.LODGING]
    assert len(lodging) == 0


def test_nearby_food_remains_lenient():
    claims = search_claims(
        [{"name": "无名小馆", "address": "龙蟠路", "tag": "生活服务"}],
        information_need="nearby_food",
        nearby_search=True,
        tag="美食",
        latitude=32.07,
    )
    food = [c for c in claims if c.claim_type == ClaimType.FOOD]
    assert len(food) == 1


def test_claims_carry_search_tag_metadata():
    claims = search_claims(
        [{"name": "如家酒店", "address": "民主北路", "tag": "酒店"}],
        information_need="nearby_hotel",
        nearby_search=True,
        tag="酒店",
        latitude=34.27,
    )
    lodging = next(c for c in claims if c.claim_type == ClaimType.LODGING)
    assert lodging.normalized_value.get("search_tag") == "酒店"
    assert lodging.normalized_value.get("baidu_item_tag") == "酒店"
