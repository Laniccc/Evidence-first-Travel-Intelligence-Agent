from __future__ import annotations

from app.schemas.evidence import ClaimType, Evidence
from app.schemas.user_query import TravelAgentState


def extract_place_candidates(evidence: list[Evidence]) -> list[dict]:
    for ev in evidence:
        for claim in ev.claims:
            if claim.claim_type != ClaimType.PLACE_CANDIDATES:
                continue
            if isinstance(claim.normalized_value, dict):
                bucket = claim.normalized_value.get("candidates")
                if isinstance(bucket, list):
                    return [c for c in bucket if isinstance(c, dict)]
            if isinstance(claim.value, list):
                return [c for c in claim.value if isinstance(c, dict)]
    return []


def _location_key(candidate: dict) -> str:
    province = (candidate.get("province") or "").strip()
    city = (candidate.get("city") or "").strip()
    name = (candidate.get("name") or "").strip()
    return f"{province}|{city}|{name}"


def detect_ambiguous_candidates(evidence: list[Evidence]) -> list[dict] | None:
    candidates = extract_place_candidates(evidence)
    if len(candidates) < 2:
        return None
    keys = {_location_key(c) for c in candidates}
    if len(keys) <= 1:
        return None
    return candidates


def candidate_display_label(candidate: dict) -> str:
    province = (candidate.get("province") or "").strip()
    city = (candidate.get("city") or "").strip()
    name = (candidate.get("name") or "").strip()
    address = (candidate.get("address") or "").strip()
    if province or city:
        label = " ".join(part for part in (province, city) if part)
        return f"{label}（{name}）" if name and name not in label else label
    if name:
        return name
    if address:
        return address
    return "未知地点"


def build_clarification_question(place_name: str, candidates: list[dict]) -> str:
    lines = [f"{place_name}有多个同名地点，你指的是哪一个？"]
    for idx, c in enumerate(candidates[:5], start=1):
        lines.append(f"{idx}. {candidate_display_label(c)}")
    return "\n".join(lines)


def try_resolve_disambiguation(state: TravelAgentState) -> bool:
    """If evidence now resolves a unique place, apply it and clear pending flag."""
    candidates = extract_place_candidates(state.evidence)
    unique = should_apply_unique_resolution(candidates)
    if not unique:
        return False
    apply_unique_candidate(state, unique)
    structured = dict(state.structured_result or {})
    state.structured_result = structured
    return True


def apply_unique_candidate(state: TravelAgentState, candidate: dict) -> TravelAgentState:
    frame = state.semantic_frame
    if not frame:
        return state
    if candidate.get("city"):
        frame.entities.city = candidate["city"]
    if candidate.get("province"):
        frame.entities.region = candidate["province"]
    if candidate.get("name") and not frame.entities.places:
        frame.entities.places = [candidate["name"]]
    if candidate.get("latitude") is not None and candidate.get("longitude") is not None:
        structured = dict(state.structured_result or {})
        structured["resolved_coordinates"] = {
            "latitude": candidate["latitude"],
            "longitude": candidate["longitude"],
        }
        state.structured_result = structured
    return state


def should_apply_unique_resolution(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    keys = {_location_key(c) for c in candidates}
    if len(keys) == 1:
        return candidates[0]
    return None
