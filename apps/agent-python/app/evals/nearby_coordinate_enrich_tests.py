"""Nearby search coordinate enrichment tests."""

from __future__ import annotations

from app.orchestrator.mcp_tool_arguments import (
    apply_nearby_anchor_coordinates,
    enrich_mcp_tool_arguments,
    nearby_coordinate_patch,
)
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from tools.mcp.adapters.baidu_response_parser import build_map_search_places_args


def _state_with_coords(*, city: str = "南京") -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="明故宫附近美食",
        entities=SemanticEntities(country="China", city=city, places=["明故宫遗址"]),
    )
    evidence = [
        Evidence(
            source_name="Baidu Maps MCP",
            source_type=SourceType.MAP,
            country="China",
            city=city,
            place_name="明故宫遗址",
            claims=[
                Claim(
                    claim_type=ClaimType.COORDINATES,
                    value={"latitude": 32.0415, "longitude": 118.8165},
                    normalized_value={"latitude": 32.0415, "longitude": 118.8165},
                    confidence=0.75,
                )
            ],
        )
    ]
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
        evidence=evidence,
    )


def test_nearby_coordinate_patch_format():
    patch = nearby_coordinate_patch({"latitude": 32.04, "longitude": 118.81})
    assert patch["latitude"] == 32.04
    assert patch["longitude"] == 118.81
    assert patch["radius"] == 3000
    assert patch["nearby_search"] is True


def test_apply_nearby_anchor_drops_region():
    args = {"query": "美食", "region": "南京", "tag": "美食"}
    apply_nearby_anchor_coordinates(args, {"latitude": 32.04, "longitude": 118.81})
    assert args["latitude"] == 32.04
    assert "region" not in args
    built = build_map_search_places_args({**args, "nearby_search": True})
    assert built["location"] == "32.04,118.81"
    assert "region" not in built


def test_enrich_nearby_injects_coords_even_when_region_present():
    state = _state_with_coords()
    args = enrich_mcp_tool_arguments(
        "baidu_place_search_mcp",
        {
            "query": "明故宫遗址 美食",
            "information_need": "nearby_food",
            "region": "南京",
            "tag": "美食",
        },
        state=state,
        prompt_context={},
    )
    assert args["latitude"] == 32.0415
    assert args["longitude"] == 118.8165
    assert args["radius"] == 3000
    assert "region" not in args
    built = build_map_search_places_args(args)
    assert built["location"] == "32.0415,118.8165"


def test_resolve_nearby_anchor_prefers_named_gate_over_scenic_center():
    from tools.mcp.adapters.baidu_response_parser import resolve_nearby_anchor_coordinates

    candidates = [
        {
            "name": "玄武湖景区",
            "latitude": 32.076613,
            "longitude": 118.805436,
        },
        {
            "name": "玄武湖景区-和平门",
            "latitude": 32.082030,
            "longitude": 118.810703,
        },
    ]
    evidence = [
        Evidence(
            source_name="Baidu Maps MCP",
            source_type=SourceType.MAP,
            country="China",
            city="南京",
            place_name="玄武湖景区",
            claims=[
                Claim(
                    claim_type=ClaimType.PLACE_CANDIDATES,
                    value=candidates,
                    normalized_value={"candidates": candidates},
                    confidence=0.6,
                )
            ],
        )
    ]
    coords = resolve_nearby_anchor_coordinates(
        evidence,
        user_query="玄武湖北门附近有什么好吃的？",
    )
    assert coords is not None
    assert abs(coords["latitude"] - 32.082030) < 0.001
    assert abs(coords["longitude"] - 118.810703) < 0.001
