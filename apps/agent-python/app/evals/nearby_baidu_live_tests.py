"""Live Baidu nearby pipeline tests — run when BAIDU_MAP_AK is configured."""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.orchestrator.information_need_aliases import infer_nearby_need_from_text
from app.orchestrator.nearby_guided_composition import collect_area_nearby_clues
from app.orchestrator.nearby_recommendation_policy import baidu_tag_for_need, is_adoptable_nearby_poi
from app.orchestrator.nearby_recommendation_policy import nearby_query_suffix_for_need as suffix_for_need
from app.schemas.evidence import ClaimType, Evidence, SourceType
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState
from app.tools.mcp.client_manager import reset_mcp_client_manager
from tools.mcp.adapters.baidu_map_adapter import BaiduMapMCPAdapter
from tools.mcp.adapters.baidu_response_parser import search_claims
from tools.mcp.registry_setup import attach_mcp_tools
from app.tools import ToolRegistry

pytestmark = pytest.mark.integration

_ANCHOR = "徐州市第三中学"
_ANCHOR_LAT = 34.269
_ANCHOR_LNG = 117.198

_SKIP = not (os.getenv("BAIDU_MAP_AK") or "").strip()


def _live_settings() -> Settings:
    return Settings(
        mcp_enabled=True,
        mcp_baidu_map_enabled=True,
        baidu_map_ak=os.environ["BAIDU_MAP_AK"].strip(),
        mcp_baidu_map_transport="baidu_streamable_http",
        mcp_baidu_map_server_url="https://mcp.map.baidu.com/mcp",
        mcp_baidu_map_timeout_seconds=15.0,
    )


@pytest.fixture
def live_baidu(monkeypatch):
    if _SKIP:
        pytest.skip("BAIDU_MAP_AK not set")
    settings = _live_settings()
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "tools.mcp.client_manager.get_settings",
        "tools.mcp.registry_setup.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    reset_mcp_client_manager()
    registry = ToolRegistry()
    attach_mcp_tools(registry)
    yield settings, registry
    reset_mcp_client_manager()


@pytest.mark.skipif(_SKIP, reason="BAIDU_MAP_AK not set")
@pytest.mark.asyncio
async def test_live_geocode_anchor(live_baidu):
    _settings, registry = live_baidu
    adapter = BaiduMapMCPAdapter("baidu_geocode_mcp")
    evidence = await adapter.run(query=_ANCHOR, city="徐州")
    assert evidence
    assert any(c.claim_type == ClaimType.ADDRESS for ev in evidence for c in ev.claims)


@pytest.mark.parametrize(
    "query,need",
    [
        (f"{_ANCHOR}附近有没有宾馆", "nearby_hotel"),
        (f"{_ANCHOR}附近公共厕所", "nearby_toilet"),
        (f"{_ANCHOR}附近停车场", "nearby_parking"),
    ],
)
@pytest.mark.skipif(_SKIP, reason="BAIDU_MAP_AK not set")
@pytest.mark.asyncio
async def test_live_nearby_search_no_cross_category_pollution(live_baidu, query, need):
    _settings, _registry = live_baidu
    assert infer_nearby_need_from_text(query) == need
    tag = baidu_tag_for_need(need)
    suffix = suffix_for_need(need)
    adapter = BaiduMapMCPAdapter("baidu_place_search_mcp")
    evidence = await adapter.run(
        query=f"{_ANCHOR} {suffix}",
        tag=tag,
        latitude=_ANCHOR_LAT,
        longitude=_ANCHOR_LNG,
        radius=2000,
        nearby_search=True,
        information_need=need,
        claim_target=need,
    )
    assert evidence
    all_claims = [c for ev in evidence for c in ev.claims]
    pc = next((c for c in all_claims if c.claim_type == ClaimType.PLACE_CANDIDATES), None)
    assert pc is not None
    candidates = pc.normalized_value.get("candidates") if isinstance(pc.normalized_value, dict) else pc.value
    typed = search_claims(
        candidates if isinstance(candidates, list) else [],
        information_need=need,
        nearby_search=True,
        tag=tag,
        latitude=_ANCHOR_LAT,
        anchor_candidate_name=_ANCHOR,
    )
    actionable = [
        c
        for c in typed
        if c.claim_type != ClaimType.PLACE_CANDIDATES and str(c.value or "").strip()
    ]
    if need == "nearby_hotel":
        for c in actionable:
            name = str(c.value).split("（")[0]
            assert is_adoptable_nearby_poi(
                name,
                need,
                anchor_place=_ANCHOR,
                poi_tag=(c.normalized_value or {}).get("baidu_item_tag"),
                search_tag=tag,
            )
            assert "中学" not in name or "酒店" in name or "宾馆" in name
    if need == "nearby_toilet":
        food_only = [c for c in actionable if "辣饼" in str(c.value) or "餐厅" in str(c.value)]
        assert not food_only


@pytest.mark.skipif(_SKIP, reason="BAIDU_MAP_AK not set")
@pytest.mark.asyncio
async def test_live_hotel_chain_short_circuit(live_baidu):
    _settings, _registry = live_baidu
    need = "nearby_hotel"
    tag = baidu_tag_for_need(need)
    adapter = BaiduMapMCPAdapter("baidu_place_search_mcp")
    evidence = await adapter.run(
        query=f"{_ANCHOR} 酒店",
        tag=tag,
        latitude=_ANCHOR_LAT,
        longitude=_ANCHOR_LNG,
        radius=2000,
        nearby_search=True,
        information_need=need,
    )
    ev = Evidence(
        evidence_id="live-ev",
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        city="徐州",
        claims=[c for e in evidence for c in e.claims],
        confidence=0.7,
    )
    state = TravelAgentState(session_id="live", query_id="q", raw_user_query=f"{_ANCHOR}附近宾馆")
    state.semantic_frame = SemanticFrame(
        raw_query=state.raw_user_query,
        normalized_request=state.raw_user_query,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.NEARBY_SEARCH,
        entities=SemanticEntities(country="China", city="徐州", places=[_ANCHOR]),
        information_needs=["nearby_hotel"],
        confidence=0.85,
    )
    state.evidence = [ev]
    clues = collect_area_nearby_clues(state)
    assert isinstance(clues, list)
