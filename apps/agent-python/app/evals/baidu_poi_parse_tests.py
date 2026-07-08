"""Baidu POI parse regression tests (nested location + truncated MCP preview)."""

from __future__ import annotations

from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from tools.mcp.adapters.baidu_response_parser import (
    parse_search_places,
    pick_baidu_uid_from_evidence,
    resolve_coordinates_from_evidence,
    search_claims,
)


_MING_PALACE_RESULT = {
    "status": 0,
    "message": "ok",
    "result_type": "poi_type",
    "query_type": "precise",
    "results": [
        {
            "name": "明故宫",
            "location": {"lat": 32.04765104836698, "lng": 118.824370648585},
            "address": "中山东路311-3号",
            "province": "江苏省",
            "city": "南京市",
            "uid": "5ac35bd4e63ef0c848cc4a1a",
        }
    ],
}


def test_parse_search_places_nested_location():
    candidates = parse_search_places(_MING_PALACE_RESULT)
    assert len(candidates) == 1
    assert candidates[0]["name"] == "明故宫"
    assert candidates[0]["uid"] == "5ac35bd4e63ef0c848cc4a1a"
    assert candidates[0]["latitude"] == 32.04765104836698
    assert candidates[0]["longitude"] == 118.824370648585


def test_parse_search_places_truncated_preview():
    blob = __import__("json").dumps(_MING_PALACE_RESULT, ensure_ascii=False)
    preview = blob[:400]
    candidates = parse_search_places({"truncated": True, "preview": preview})
    assert candidates
    assert candidates[0]["name"] == "明故宫"
    assert candidates[0]["uid"] == "5ac35bd4e63ef0c848cc4a1a"
    assert candidates[0]["latitude"] is not None
    assert candidates[0]["longitude"] is not None


def test_search_claims_include_coordinates_and_uid():
    claims = search_claims(parse_search_places(_MING_PALACE_RESULT))
    types = {c.claim_type for c in claims}
    assert ClaimType.PLACE_CANDIDATES in types
    assert ClaimType.POI_UID in types
    assert ClaimType.COORDINATES in types


def test_resolve_coordinates_from_legacy_travel_advice_blob():
    import json

    ev = Evidence(
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        place_name="明故宫遗址",
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value=json.dumps(_MING_PALACE_RESULT, ensure_ascii=False)[:600],
                confidence=0.55,
            )
        ],
    )
    coords = resolve_coordinates_from_evidence([ev])
    assert coords is not None
    assert abs(coords["latitude"] - 32.04765104836698) < 1e-6
    uid = pick_baidu_uid_from_evidence([ev])
    assert uid == "5ac35bd4e63ef0c848cc4a1a"


def test_detail_claims_include_coordinates():
    from tools.mcp.adapters.baidu_response_parser import detail_claims, parse_place_details

    detail = parse_place_details({"result": _MING_PALACE_RESULT["results"][0]})
    claims = detail_claims(detail)
    types = {c.claim_type for c in claims}
    assert ClaimType.COORDINATES in types


def test_resolve_coordinates_from_structured_result_fallback():
    coords = resolve_coordinates_from_evidence(
        [],
        structured_result={"resolved_coordinates": {"latitude": 32.04, "longitude": 118.81}},
    )
    assert coords == {"latitude": 32.04, "longitude": 118.81}


def test_parse_geocode_truncated_preview():
    from tools.mcp.adapters.baidu_response_parser import parse_geocode

    payload = {
        "truncated": True,
        "preview": '{"result":{"location":{"lat":32.04,"lng":118.81},"formatted_address":"南京"}}',
    }
    parsed = parse_geocode(payload)
    assert parsed["latitude"] == 32.04
    assert parsed["longitude"] == 118.81
