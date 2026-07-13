from types import SimpleNamespace

from app.evidence.evidence_model import ClaimType
from app.evidence.poi_anchor_extraction import (
    candidates_are_ambiguous,
    gate_tokens_from_user_query,
    resolve_coordinates_from_evidence,
    resolve_nearby_anchor_coordinates,
)


def _evidence_with_candidates(candidates: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        claims=[
            SimpleNamespace(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value=None,
                normalized_value={"candidates": candidates},
            )
        ]
    )


def test_nearby_anchor_prefers_requested_gate_coordinate():
    evidence = _evidence_with_candidates(
        [
            {"name": "\u516c\u56ed\u5357\u95e8", "latitude": 32.01, "longitude": 118.01},
            {"name": "\u516c\u56ed\u5317\u95e8", "latitude": 32.02, "longitude": 118.02},
        ]
    )

    assert gate_tokens_from_user_query("\u8bf7\u627e\u5317\u95e8\u9644\u8fd1\u7684\u9910\u5385")[-1] == "\u5317\u95e8"
    assert resolve_nearby_anchor_coordinates([evidence], user_query="\u5317\u95e8\u9644\u8fd1") == {
        "latitude": 32.02,
        "longitude": 118.02,
    }


def test_coordinate_resolution_falls_back_to_structured_result():
    assert resolve_coordinates_from_evidence(
        [], structured_result={"resolved_coordinates": {"lat": "31.23", "lng": "121.47"}}
    ) == {"latitude": 31.23, "longitude": 121.47}


def test_candidate_ambiguity_requires_distinct_location_keys():
    assert not candidates_are_ambiguous(
        [
            {"province": "\u6c5f\u82cf", "city": "\u5357\u4eac", "name": "\u4e2d\u5c71\u9675"},
            {"province": "\u6c5f\u82cf", "city": "\u5357\u4eac", "name": "\u4e2d\u5c71\u9675"},
        ]
    )
    assert candidates_are_ambiguous(
        [
            {"province": "\u6c5f\u82cf", "city": "\u5357\u4eac", "name": "\u4e2d\u5c71\u9675"},
            {"province": "\u5317\u4eac", "city": "\u5317\u4eac", "name": "\u4e2d\u5c71\u9675"},
        ]
    )
