"""Baidu POI taxonomy integration tests."""

from __future__ import annotations

from app.orchestrator.information_need_aliases import infer_all_nearby_needs_from_text, infer_nearby_need_from_text
from app.orchestrator.nearby_category_registry import (
    baidu_tag_for_category,
    get_category,
    query_suffix_for_category,
    taxonomy_meta_for_need,
)
from app.orchestrator.baidu_poi_taxonomy import load_taxonomy_entries
from tools.mcp.adapters.nearby_poi_claims import append_nearby_recommendation_claims
from app.schemas.evidence import ClaimType


def test_baidu_taxonomy_loads_travel_entries():
    entries = load_taxonomy_entries()
    needs = {e.canonical_need for e in entries}
    assert "nearby_food" in needs
    assert "nearby_library" in needs
    assert len(entries) >= 14


def test_library_uses_baidu_education_industry():
    q = "徐州市第三中学附近有没有图书馆？"
    assert infer_nearby_need_from_text(q) == "nearby_library"
    cat = get_category("nearby_library")
    assert cat is not None
    assert cat.baidu_primary_industry == "教育培训"
    assert "图书馆" in cat.baidu_secondary_tags
    assert cat.baidu_tag == "教育培训"
    assert query_suffix_for_category("nearby_library") == "图书馆"


def test_toilet_uses_baidu_life_service_industry():
    q = "徐州市第三中学附近有没有公共厕所？"
    assert infer_nearby_need_from_text(q) == "nearby_toilet"
    cat = get_category("nearby_toilet")
    assert cat is not None
    assert cat.baidu_primary_industry == "生活服务"
    assert "公共厕所" in cat.baidu_secondary_tags
    assert baidu_tag_for_category("nearby_toilet") == "生活服务"


def test_generic_nearby_no_misleading_tag():
    assert infer_nearby_need_from_text("附近有什么") == "nearby_poi"
    assert baidu_tag_for_category("nearby_poi") is None


def test_taxonomy_metadata_on_claims():
    claims: list = []
    append_nearby_recommendation_claims(
        claims,
        [{"name": "徐州图书馆", "address": "淮海路", "tag": "图书馆"}],
        "nearby_library",
        search_tag="教育培训",
    )
    typed = [c for c in claims if c.claim_type == ClaimType.GENERAL_FACT]
    assert len(typed) == 1
    nv = typed[0].normalized_value
    assert nv.get("taxonomy_schema") == "baidu_poitags_v1"
    assert nv.get("baidu_primary_industry") == "教育培训"
    assert "图书馆" in (nv.get("baidu_secondary_tags") or "")


def test_compound_food_and_parking():
    needs = infer_all_nearby_needs_from_text("好吃的和停车场")
    assert "nearby_food" in needs
    assert "nearby_parking" in needs


def test_taxonomy_meta_for_food():
    meta = taxonomy_meta_for_need("nearby_food")
    assert meta["taxonomy_schema"] == "baidu_poitags_v1"
    assert meta["baidu_primary_industry"] == "美食"


def test_food_enrichment_fields_from_taxonomy():
    from app.orchestrator.nearby_category_registry import (
        enrichment_enabled_for_category,
        enrichment_tools_for_category,
        enrichment_top_n_for_category,
    )

    assert enrichment_enabled_for_category("nearby_food")
    assert "baidu_place_detail_mcp" in enrichment_tools_for_category("nearby_food")
    assert enrichment_top_n_for_category("nearby_food") == 5
