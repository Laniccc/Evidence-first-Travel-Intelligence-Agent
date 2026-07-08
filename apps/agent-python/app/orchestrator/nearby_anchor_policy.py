"""Nearby retrieval anchor policy: precise point vs fuzzy area vs per-candidate search."""

from __future__ import annotations

from app.orchestrator.information_need_aliases import is_nearby_need, normalize_need
from app.orchestrator.place_disambiguation_guard import _location_key
from app.schemas.user_query import TravelAgentState
from tools.mcp.adapters.baidu_response_parser import (
    gate_tokens_from_user_query,
    resolve_nearby_anchor_coordinates,
)

_MAX_PER_CANDIDATE_SEARCHES = 5
_DEFAULT_RADIUS_M = 3000
_GATE_RADIUS_M = 1500
_SUBPOI_RADIUS_M = 1200
_PARKING_RADIUS_M = 800


def anchor_place_name(state: TravelAgentState) -> str:
    frame = state.semantic_frame
    if frame and frame.entities and frame.entities.places:
        return (frame.entities.places[0] or "").strip()
    return (state.raw_user_query or "")[:48].strip()


def same_scenic_area_sub_poi_ambiguity(candidates: list[dict], anchor_place: str) -> bool:
    """Multiple POIs under one scenic anchor (gates, parking) vs cross-city homonyms."""
    anchor = (anchor_place or "").strip()
    if len(candidates) < 2:
        return False
    if anchor:
        related = sum(
            1
            for c in candidates
            if anchor in (c.get("name") or "") or anchor in (c.get("address") or "")
        )
        if related >= 2:
            return True
    cities = {(c.get("city") or "").strip() for c in candidates}
    cities.discard("")
    if len(cities) == 1 and cities:
        return True
    return False


def _candidate_coords(candidate: dict) -> dict[str, float] | None:
    lat, lng = candidate.get("latitude"), candidate.get("longitude")
    if lat is None or lng is None:
        return None
    return {"latitude": float(lat), "longitude": float(lng)}


def _candidate_matches_gate(candidate: dict, user_query: str) -> bool:
    tokens = gate_tokens_from_user_query(user_query)
    if not tokens:
        return False
    label = f"{candidate.get('name') or ''} {candidate.get('address') or ''}"
    return any(token in label for token in tokens)


def _radius_for_candidate(candidate: dict) -> int:
    name = str(candidate.get("name") or "")
    if "停车场" in name or "停车" in name:
        return _PARKING_RADIUS_M
    if any(g in name for g in ("门", "山门", "北门", "南门", "售票")):
        return _GATE_RADIUS_M
    return _SUBPOI_RADIUS_M


def build_nearby_search_targets(
    state: TravelAgentState,
    candidates: list[dict],
    *,
    nearby_claim: str,
    evidence_list: list | None = None,
) -> dict:
    """
    Plan Baidu / Dianping nearby searches.

    Returns search_mode and search_targets (each with coordinates, candidate, location_key, radius).
    """
    user_query = state.raw_user_query or ""
    anchor = anchor_place_name(state)
    claim = normalize_need(nearby_claim)
    merged = list(evidence_list or []) + list(state.evidence or [])

    targets: list[dict] = []
    search_mode = "precise_point"

    if len(candidates) >= 2 and same_scenic_area_sub_poi_ambiguity(candidates, anchor):
        search_mode = "per_candidate_precise"
        for candidate in candidates[:_MAX_PER_CANDIDATE_SEARCHES]:
            coords = _candidate_coords(candidate)
            if not coords:
                continue
            targets.append(
                {
                    "search_mode": "precise_point",
                    "coordinates": coords,
                    "candidate": dict(candidate),
                    "location_key": _location_key(candidate),
                    "candidate_name": (candidate.get("name") or anchor or "").strip(),
                    "radius": _radius_for_candidate(candidate),
                    "rationale": "同景区多 POI 消歧：为每个候选锚点分别检索周边",
                }
            )
    else:
        gate_hits = [c for c in candidates if _candidate_matches_gate(c, user_query)]
        if gate_hits:
            search_mode = "gate_precise"
            for candidate in gate_hits[:3]:
                coords = _candidate_coords(candidate)
                if not coords:
                    continue
                targets.append(
                    {
                        "search_mode": "precise_point",
                        "coordinates": coords,
                        "candidate": dict(candidate),
                        "location_key": _location_key(candidate),
                        "candidate_name": (candidate.get("name") or "").strip(),
                        "radius": _GATE_RADIUS_M,
                        "rationale": "用户提及门点/方位，以对应门点坐标精确检索",
                    }
                )
        else:
            coords = resolve_nearby_anchor_coordinates(
                merged,
                user_query=user_query,
                structured_result=state.structured_result,
            )
            if coords:
                fuzzy = "附近" in user_query and not gate_tokens_from_user_query(user_query)
                search_mode = "fuzzy_area" if fuzzy else "precise_point"
                targets.append(
                    {
                        "search_mode": search_mode,
                        "coordinates": coords,
                        "candidate": {},
                        "location_key": "",
                        "candidate_name": anchor,
                        "radius": _DEFAULT_RADIUS_M if fuzzy else _SUBPOI_RADIUS_M,
                        "rationale": "以解析锚点为中心做周边圆形检索"
                        if not fuzzy
                        else "用户仅说「附近」无具体门点，适度放大检索半径",
                    }
                )

    if not targets and candidates:
        coords = _candidate_coords(candidates[0])
        if coords:
            targets.append(
                {
                    "search_mode": "precise_point",
                    "coordinates": coords,
                    "candidate": dict(candidates[0]),
                    "location_key": _location_key(candidates[0]),
                    "candidate_name": (candidates[0].get("name") or anchor or "").strip(),
                    "radius": _SUBPOI_RADIUS_M,
                    "rationale": "回退到首个 POI 候选坐标",
                }
            )

    return {
        "nearby_claim": claim,
        "search_mode": search_mode,
        "per_candidate": search_mode == "per_candidate_precise",
        "search_targets": targets,
        "anchor_place": anchor,
        "is_food_nearby": claim in {"nearby_food", "nearby_dining", "restaurant_recommendation", "food_nearby"},
    }

