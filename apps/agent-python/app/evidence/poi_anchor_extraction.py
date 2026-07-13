"""Tool-neutral extraction of nearby-search anchors from evidence."""

from __future__ import annotations

import re
from typing import Any

from app.evidence.evidence_model import ClaimType


_NEARBY_QUALIFIER_PATTERNS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"\u5317\u95e8|\u7384\u6b66\u95e8|\u548c\u5e73\u95e8"), ("\u548c\u5e73\u95e8", "\u7384\u6b66\u95e8", "\u5317\u95e8")),
    (re.compile(r"\u89e3\u653e\u95e8"), ("\u89e3\u653e\u95e8",)),
    (re.compile(r"\u60c5\u4fa3\u56ed\u95e8|\u60c5\u4fa3\u56ed"), ("\u60c5\u4fa3\u56ed",)),
    (re.compile(r"\u592a\u5e73\u95e8"), ("\u592a\u5e73\u95e8",)),
    (re.compile(r"\u5357\u95e8|\u6b63\u5927\u95e8|\u4e3b\u5165\u53e3"), ("\u6b63\u95e8", "\u5357\u95e8", "\u4e3b\u5165\u53e3")),
    (re.compile(r"\u4e1c\u95e8"), ("\u4e1c\u95e8",)),
    (re.compile(r"\u897f\u95e8"), ("\u897f\u95e8",)),
]
_POI_LAT_RE = re.compile(r'"(?:lat|latitude)"\s*:\s*([-\d.]+)')
_POI_LNG_RE = re.compile(r'"(?:lng|lon|longitude)"\s*:\s*([-\d.]+)')


def gate_tokens_from_user_query(user_query: str) -> tuple[str, ...]:
    """Return named gate qualifiers in a query, preserving their policy order."""
    text = (user_query or "").strip()
    if not text:
        return ()
    tokens: list[str] = []
    for pattern, names in _NEARBY_QUALIFIER_PATTERNS:
        if pattern.search(text):
            tokens.extend(names)
    return tuple(dict.fromkeys(tokens))


def candidates_are_ambiguous(candidates: list[dict[str, Any]]) -> bool:
    """Whether a candidate set represents more than one concrete place."""
    if len(candidates) < 2:
        return False
    keys = {
        "|".join(
            (
                str(candidate.get("province") or "").strip(),
                str(candidate.get("city") or "").strip(),
                str(candidate.get("name") or "").strip(),
            )
        )
        for candidate in candidates
    }
    return len(keys) > 1


def resolve_nearby_anchor_coordinates(
    evidence_list: list[Any],
    *,
    user_query: str = "",
    structured_result: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    """Prefer the requested gate coordinate, then fall back to the first resolved anchor."""
    gate_tokens = gate_tokens_from_user_query(user_query)
    if gate_tokens:
        for evidence in evidence_list:
            for claim in getattr(evidence, "claims", []) or []:
                if not _has_claim_type(claim, ClaimType.PLACE_CANDIDATES):
                    continue
                for candidate in _place_candidates_from_claim(claim):
                    label = " ".join(
                        filter(None, (str(candidate.get("name") or ""), str(candidate.get("address") or "")))
                    )
                    if label and any(token in label for token in gate_tokens):
                        coordinates = _coordinates_from_candidate(candidate)
                        if coordinates:
                            return coordinates
    return resolve_coordinates_from_evidence(evidence_list, structured_result=structured_result)


def resolve_coordinates_from_evidence(
    evidence_list: list[Any],
    *,
    structured_result: dict[str, Any] | None = None,
) -> dict[str, float] | None:
    """Resolve the first trustworthy coordinate from collected evidence or state."""
    for evidence in evidence_list:
        for claim in getattr(evidence, "claims", []) or []:
            if _has_claim_type(claim, ClaimType.COORDINATES):
                coordinates = _coordinates_from_value(getattr(claim, "normalized_value", None))
                coordinates = coordinates or _coordinates_from_value(getattr(claim, "value", None))
                if coordinates:
                    return coordinates
            if _has_claim_type(claim, ClaimType.PLACE_CANDIDATES):
                for candidate in _place_candidates_from_claim(claim):
                    coordinates = _coordinates_from_candidate(candidate)
                    if coordinates:
                        return coordinates
            if _has_claim_type(claim, ClaimType.TRAVEL_ADVICE):
                coordinates = _coordinates_from_value(getattr(claim, "value", None))
                if coordinates:
                    return coordinates
    if isinstance(structured_result, dict):
        coordinates = _coordinates_from_value(structured_result.get("resolved_coordinates"))
        if coordinates:
            return coordinates
    return None


def _has_claim_type(claim: Any, expected: ClaimType) -> bool:
    actual = getattr(claim, "claim_type", None)
    return actual == expected or getattr(actual, "value", actual) == expected.value


def _coordinates_from_value(value: Any) -> dict[str, float] | None:
    if isinstance(value, dict):
        latitude = value.get("latitude") if value.get("latitude") is not None else value.get("lat")
        longitude = value.get("longitude") if value.get("longitude") is not None else value.get("lng")
        return _as_coordinates(latitude, longitude)
    if isinstance(value, str) and "results" in value:
        latitudes = _POI_LAT_RE.findall(value)
        longitudes = _POI_LNG_RE.findall(value)
        if latitudes and longitudes:
            return _as_coordinates(latitudes[0], longitudes[0])
    return None


def _coordinates_from_candidate(candidate: dict[str, Any]) -> dict[str, float] | None:
    return _as_coordinates(candidate.get("latitude"), candidate.get("longitude"))


def _as_coordinates(latitude: Any, longitude: Any) -> dict[str, float] | None:
    if latitude is None or longitude is None:
        return None
    try:
        return {"latitude": float(latitude), "longitude": float(longitude)}
    except (TypeError, ValueError):
        return None


def _place_candidates_from_claim(claim: Any) -> list[dict[str, Any]]:
    bucket = getattr(claim, "normalized_value", None) or getattr(claim, "value", None)
    if isinstance(bucket, dict):
        bucket = bucket.get("candidates") or []
    if isinstance(bucket, list):
        return [candidate for candidate in bucket if isinstance(candidate, dict)]
    return []
