"""Geo anchor for strict_fact_lookup — POI resolution via evidence, no place-specific fact tables."""

from __future__ import annotations

import re

from app.orchestrator.place_disambiguation_guard import (
    apply_unique_candidate,
    extract_place_candidates,
)
from app.schemas.user_query import TravelAgentState

_ADMIN_DEPRIORITIZE = re.compile(r"市人民政府|区政府|火车站|高铁站|机场|人民政府")
_SCENIC_BOOST = re.compile(r"风景区|景区|国家公园|森林公园|自然保护区")
_NUMERIC_ELEVATION = re.compile(r"\d{3,4}(?:\.\d+)?\s*米")
_PARTIAL_ELEVATION_HINTS = re.compile(r"公路|余脉|灌木|山脚|索道下|换乘")
_NON_ELEVATION_NOISE = re.compile(r"平方千米|经纬度|总面积|南北长约|东西宽约|管理区")

GEO_FACT_NEEDS = frozenset({"elevation"})


def is_geographic_fact_need(need: str | None) -> bool:
    return str(need or "").strip() in GEO_FACT_NEEDS


def raw_place_label(state: TravelAgentState) -> str:
    frame = state.semantic_frame
    if frame and frame.entities and frame.entities.places:
        return (frame.entities.places[0] or "").strip()
    return (state.raw_user_query or "")[:48].strip()


def resolved_place_label(state: TravelAgentState) -> str:
    structured = state.structured_result or {}
    anchor = structured.get("fact_anchor") or {}
    resolved = (anchor.get("resolved_name") or "").strip()
    if resolved:
        return resolved
    return raw_place_label(state)


def interpret_place_for_fact_need(place: str, need: str) -> str:
    """Use anchored POI name when available; do not rewrite via static place tables."""
    return (place or "").strip()


def place_scope_note(state: TravelAgentState, need: str) -> str | None:
    if need != "elevation":
        return None
    structured = state.structured_result or {}
    anchor = structured.get("fact_anchor") or {}
    raw = (anchor.get("raw_place") or raw_place_label(state)).strip()
    resolved = (anchor.get("resolved_name") or "").strip()
    if resolved and resolved != raw:
        return (
            f"本轮将「{raw}」锚定为「{resolved}」；"
            "海拔问题应针对该景区/山体实体，勿与同名行政区或其它地点混淆。"
        )
    return None


def needs_geo_anchor(state: TravelAgentState) -> bool:
    from app.orchestrator.fact_lookup_policy import is_fact_lookup_task

    if not is_fact_lookup_task(state):
        return False
    structured = state.structured_result or {}
    if structured.get("fact_anchor"):
        return False
    frame = state.semantic_frame
    if not frame or not frame.entities or not frame.entities.places:
        return False
    city = (frame.entities.city or "").strip()
    region = (frame.entities.region or "").strip()
    candidates = extract_place_candidates(list(state.evidence or []))
    if candidates and city and region:
        return False
    return not city or not candidates


def _score_fact_anchor_candidate(candidate: dict, *, raw_place: str, need: str) -> int:
    name = str(candidate.get("name") or "")
    address = str(candidate.get("address") or "")
    label = f"{name} {address}"
    score = 0
    if raw_place and raw_place in name:
        score += 4
    if _SCENIC_BOOST.search(label):
        score += 12
    if need == "elevation" and name.endswith("山"):
        score += 6
    if _ADMIN_DEPRIORITIZE.search(label):
        score -= 14
    if need == "elevation" and raw_place + "市" in name and "风景区" not in name:
        score -= 10
    tag = str(candidate.get("tag") or candidate.get("type") or "")
    if need == "elevation" and any(x in tag for x in ("行政", "区县")):
        score -= 8
    return score


def select_fact_anchor_candidate(
    candidates: list[dict],
    *,
    raw_place: str,
    need: str,
) -> dict | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    ranked = sorted(
        candidates,
        key=lambda c: _score_fact_anchor_candidate(c, raw_place=raw_place, need=need),
        reverse=True,
    )
    best = ranked[0]
    best_score = _score_fact_anchor_candidate(best, raw_place=raw_place, need=need)
    if best_score <= 0:
        return None
    second_score = _score_fact_anchor_candidate(ranked[1], raw_place=raw_place, need=need)
    if best_score - second_score < 3:
        return None
    return best


def apply_fact_anchor_candidate(
    state: TravelAgentState,
    candidate: dict,
    *,
    need: str,
) -> TravelAgentState:
    raw = raw_place_label(state)
    apply_unique_candidate(state, candidate)
    frame = state.semantic_frame
    resolved_name = (candidate.get("name") or raw).strip()
    if frame and frame.entities and resolved_name:
        frame.entities.places = [resolved_name]
    structured = dict(state.structured_result or {})
    structured["fact_anchor"] = {
        "raw_place": raw,
        "resolved_name": resolved_name,
        "search_place": resolved_name or raw,
        "city": candidate.get("city"),
        "province": candidate.get("province"),
        "information_need": need,
        "latitude": candidate.get("latitude"),
        "longitude": candidate.get("longitude"),
    }
    state.structured_result = structured
    return state


def apply_fact_anchor_from_evidence(state: TravelAgentState, need: str) -> bool:
    candidates = extract_place_candidates(list(state.evidence or []))
    raw = raw_place_label(state)
    chosen = select_fact_anchor_candidate(candidates, raw_place=raw, need=need)
    if not chosen:
        return False
    apply_fact_anchor_candidate(state, chosen, need=need)
    return True


def elevation_clue_rank(text: str, *, authoritative_geo: bool = False, official: bool = False) -> int:
    rank = 0
    if official:
        rank += 20
    if authoritative_geo:
        rank += 15
    if _NUMERIC_ELEVATION.search(text):
        rank += 8
    if _PARTIAL_ELEVATION_HINTS.search(text):
        rank -= 12
    if _NON_ELEVATION_NOISE.search(text) and not _NUMERIC_ELEVATION.search(text):
        rank -= 15
    return rank
