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


def build_clarification_question(place_name: str, candidates: list[dict]) -> str:
    lines = [f"{place_name}有多个同名地点，你指的是哪个省市的{place_name}？"]
    for idx, c in enumerate(candidates[:5], start=1):
        province = c.get("province") or "未知省份"
        city = c.get("city") or "未知城市"
        address = c.get("address") or ""
        suffix = f"（{address}）" if address else ""
        lines.append(f"{idx}. {province} {city}{suffix}")
    return "\n".join(lines)


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
