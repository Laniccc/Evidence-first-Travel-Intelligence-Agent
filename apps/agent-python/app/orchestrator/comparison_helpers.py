"""Helpers for multi-place comparison retrieval and homonym filtering."""

from __future__ import annotations

import re
from urllib.parse import unquote

from app.config import get_settings
from app.schemas.evidence import Evidence
from app.schemas.semantic_frame import SemanticFrame
from app.schemas.user_query import TravelAgentState

# Baike URL for the Chinese character 禾 (not 禾木村)
_HOMONYM_BAIKE_PATTERNS = (
    re.compile(r"/item/%E7%A6%BE(?:/|$)", re.I),
    re.compile(r"/item/禾(?:/|$)", re.I),
)

_HOMONYM_CONTENT_MARKERS = re.compile(
    r"汉字部首|象形字|汉语文字|字的拼音|部首之一|嘉穀|专指稻子",
    re.I,
)

_TRAVEL_CONTENT_MARKERS = re.compile(
    r"景区|古镇|村落|旅游|门票|自驾|攻略|秋色|风景|游客|住宿|交通",
    re.I,
)

_NEED_QUERY_SUFFIX: dict[str, str] = {
    "crowd_level": "旅游旺季 拥挤程度 游客评价",
    "transit": "交通 怎么去 自驾",
    "transport_planning": "交通 怎么去 自驾",
    "route_plan": "交通 路线 自驾",
    "review_summary": "游客评价 值不值得去",
    "value_for_money": "值不值得去 游客评价",
    "commercialization_risk": "商业化 游客评价",
}


def is_comparison_mode(state: TravelAgentState) -> bool:
    if state.comparison_mode:
        return True
    profile = state.intent_profile
    if profile and profile.primary_intent.value == "comparison":
        return True
    frame = state.semantic_frame
    if frame and frame.task_family.value == "comparison":
        return True
    task = state.travel_task
    if task and task.task_type.value == "compare_places":
        return True
    return False


def active_place_name(state: TravelAgentState) -> str | None:
    if state.comparison_active_place:
        return state.comparison_active_place
    frame = state.semantic_frame
    if frame and frame.entities.places:
        return frame.entities.places[0]
    return None


def place_geo_tokens(frame: SemanticFrame | None) -> list[str]:
    if not frame or not frame.entities:
        return []
    tokens: list[str] = []
    for value in (frame.entities.region, frame.entities.city, frame.entities.country):
        token = str(value or "").strip()
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def disambiguated_place_label(
    place: str,
    *,
    city: str | None = None,
    region: str | None = None,
    country: str | None = None,
) -> str:
    """Full place label for search anchors (region/city + place)."""
    parts: list[str] = []
    for token in (region, city, country):
        t = str(token or "").strip()
        if t and t not in parts and t not in place:
            parts.append(t)
    place = str(place).strip()
    if place and place not in parts:
        parts.append(place)
    return " ".join(parts)


def comparison_search_anchors(
    place: str,
    frame: SemanticFrame | None,
    *,
    peer_places: list[str] | None = None,
) -> list[str]:
    peers = [p for p in (peer_places or []) if p and p != place]
    label = disambiguated_place_label(
        place,
        city=frame.entities.city if frame and frame.entities else None,
        region=frame.entities.region if frame and frame.entities else None,
        country=frame.entities.country if frame and frame.entities else None,
    )
    anchors = [label, place]
    if len(place) >= 3:
        anchors.append(place)
    anchors.extend(place_geo_tokens(frame))
    for peer in peers[:2]:
        anchors.append(peer)
    return list(dict.fromkeys(a for a in anchors if a and len(a) >= 2))


def build_comparison_search_query(
    place: str,
    information_need: str,
    frame: SemanticFrame | None,
    *,
    peer_places: list[str] | None = None,
    user_query: str | None = None,
) -> str:
    label = disambiguated_place_label(
        place,
        city=frame.entities.city if frame and frame.entities else None,
        region=frame.entities.region if frame and frame.entities else None,
        country=frame.entities.country if frame and frame.entities else None,
    )
    suffix = _NEED_QUERY_SUFFIX.get(information_need, information_need.replace("_", " "))
    peers = [p for p in (peer_places or []) if p and p != place]
    if information_need == "crowd_level" and len(peers) == 1:
        return f"{label} 与 {peers[0]} {suffix}"
    if user_query and ("选一个" in user_query or "对比" in user_query):
        return f"{label} {suffix}"
    return f"{label} {suffix}"


def is_homonym_polluted(evidence: Evidence, target_place: str) -> bool:
    """True when evidence is likely a homonym hit (e.g. 禾 vs 禾木村)."""
    place = str(target_place).strip()
    if len(place) < 3:
        return False

    url = unquote(str(evidence.source_url or ""))
    for pattern in _HOMONYM_BAIKE_PATTERNS:
        if pattern.search(url) and "禾木" not in url and "喀纳斯" not in url:
            return True

    blob_parts = [url, str(evidence.place_name or "")]
    for claim in evidence.claims:
        blob_parts.append(str(claim.value or ""))
        blob_parts.append(str(claim.raw_text or ""))
    blob = " ".join(blob_parts)

    if place in blob or place[:2] in blob:
        if _HOMONYM_CONTENT_MARKERS.search(blob) and not _TRAVEL_CONTENT_MARKERS.search(blob):
            return True
        return False

    if _HOMONYM_CONTENT_MARKERS.search(blob) and not _TRAVEL_CONTENT_MARKERS.search(blob):
        return True

    # Short place token matched only as substring of unrelated content
    short_core = place.replace("村", "").replace("景区", "").replace("镇", "")
    if len(short_core) <= 2 and short_core in blob:
        if _HOMONYM_CONTENT_MARKERS.search(blob):
            return True

    return False


def filter_polluted_evidence(evidence_list: list, target_place: str) -> list:
    if not target_place:
        return list(evidence_list)
    kept: list = []
    for item in evidence_list:
        if not isinstance(item, Evidence):
            kept.append(item)
            continue
        if is_homonym_polluted(item, target_place):
            continue
        kept.append(item)
    return kept


def stamp_evidence_place(evidence_list: list, place_name: str) -> list:
    if not place_name:
        return evidence_list
    stamped: list = []
    for item in evidence_list:
        if not isinstance(item, Evidence):
            stamped.append(item)
            continue
        if not item.place_name:
            stamped.append(item.model_copy(update={"place_name": place_name}))
        else:
            stamped.append(item)
    return stamped


def reset_per_place_search_state(state: TravelAgentState) -> None:
    """Clear S5 search loop counters so each compare place gets a full retrieval pass."""
    structured = dict(state.structured_result or {})
    for key in (
        "completed_search_task_ids",
        "keyword_search_results",
        "search_tasks",
        "recent_keyword_search_results",
    ):
        structured.pop(key, None)
    state.structured_result = structured
    state.evidence_planning_completed = False
    state.evidence_decision_report = None
    state.evidence_brief = None
    state.gap_loop_state = None


def comparison_max_tool_calls() -> int:
    settings = get_settings()
    return max(settings.mcp_max_tool_calls_per_state, settings.mcp_max_tool_calls_comparison)


_COMPARISON_DIMENSIONS = ("crowd_level", "route_plan", "review_summary")

_CLAIM_TO_COMPARISON_DIMENSION: dict[str, str] = {
    "crowd_level": "crowd_level",
    "current_crowd": "crowd_level",
    "queue_time": "crowd_level",
    "review_summary": "review_summary",
    "review_aspect": "review_summary",
    "route_plan": "route_plan",
    "transit": "route_plan",
    "duration": "route_plan",
    "distance": "route_plan",
}

_CROWD_VALUE_MARKERS = re.compile(r"拥挤|人多|旺季|排队|游客|人流", re.I)
_ROUTE_VALUE_MARKERS = re.compile(r"交通|自驾|公交|大巴|公里|小时|路线|怎么去", re.I)
_REVIEW_VALUE_MARKERS = re.compile(r"评价|攻略|值得|避坑|体验|住宿|风景", re.I)


def _travel_advice_dimension(value: str) -> str | None:
    if _CROWD_VALUE_MARKERS.search(value):
        return "crowd_level"
    if _ROUTE_VALUE_MARKERS.search(value):
        return "route_plan"
    if _REVIEW_VALUE_MARKERS.search(value):
        return "review_summary"
    return None


def places_match(label: str, candidate: str) -> bool:
    """Loose place label match (禾木村 ↔ 禾木, 喀纳斯景区 ↔ 喀纳斯)."""
    label = str(label or "").strip()
    candidate = str(candidate or "").strip()
    if not label or not candidate:
        return False
    if label == candidate or label in candidate or candidate in label:
        return True
    for suffix in ("村", "景区", "镇", "乡", "湖"):
        core_a = label.removesuffix(suffix)
        core_b = candidate.removesuffix(suffix)
        if len(core_a) >= 2 and (core_a == core_b or core_a in core_b or core_b in core_a):
            return True
    return False


def _place_matches_evidence(place: str, ev: Evidence) -> bool:
    place = str(place).strip()
    if not place:
        return False
    if ev.place_name and (place in ev.place_name or ev.place_name in place):
        return True
    blob = " ".join(
        str(part)
        for part in (
            ev.place_name,
            ev.source_url,
            *(str(c.value or "") for c in ev.claims),
        )
    )
    core = place.replace("村", "").replace("景区", "").replace("镇", "")
    return place in blob or (len(core) >= 2 and core in blob)


def curate_comparison_claim_rows(
    evidence: list,
    places: list[str],
    *,
    existing_rows: list | None = None,
    max_per_place_dim: int = 2,
) -> list:
    from app.orchestrator.claim_search_planner import is_search_miss_value
    from app.schemas.evidence_brief import CuratedClaimRow

    rows: list[CuratedClaimRow] = []
    if existing_rows:
        for item in existing_rows:
            if isinstance(item, CuratedClaimRow):
                rows.append(item)
            elif isinstance(item, dict):
                rows.append(CuratedClaimRow.model_validate(item))

    seen: set[tuple[str, str, str]] = {
        (str(r.place_name or ""), r.claim_type, r.evidence_id) for r in rows
    }
    bucket_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        dim = _CLAIM_TO_COMPARISON_DIMENSION.get(row.claim_type, row.claim_type)
        bucket_counts[(str(row.place_name or ""), dim)] = bucket_counts.get(
            (str(row.place_name or ""), dim), 0
        ) + 1

    for place in places:
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            if is_homonym_polluted(ev, place):
                continue
            if not _place_matches_evidence(place, ev):
                continue
            for claim in ev.claims:
                value = str(claim.value or "").strip()
                if not value or is_search_miss_value(value):
                    continue
                ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
                dim = _CLAIM_TO_COMPARISON_DIMENSION.get(ct)
                if ct == "travel_advice" and not dim:
                    dim = _travel_advice_dimension(value)
                if dim not in _COMPARISON_DIMENSIONS:
                    continue
                key = (place, dim, ev.evidence_id)
                if key in seen:
                    continue
                if bucket_counts.get((place, dim), 0) >= max_per_place_dim:
                    continue
                conf = float(getattr(claim, "confidence", None) or ev.confidence or 0.5)
                rows.append(
                    CuratedClaimRow(
                        claim_type=dim,
                        value=value[:500],
                        evidence_id=ev.evidence_id,
                        source_name=ev.source_name,
                        source_url=ev.source_url,
                        confidence=conf,
                        relevance_score=0.7,
                        rationale=f"comparison bucket {dim} for {place}",
                        place_name=place,
                    )
                )
                seen.add(key)
                bucket_counts[(place, dim)] = bucket_counts.get((place, dim), 0) + 1

    rows.sort(key=lambda r: (r.place_name or "", r.claim_type, -r.relevance_score, -r.confidence))
    return rows


def enrich_comparison_brief(state: TravelAgentState, brief, target_label: str):
    from app.schemas.evidence_brief import EvidenceBrief

    places = comparison_places_from_state(state)
    if len(places) < 2:
        return brief
    structured = state.structured_result or {}
    filter_rows = structured.get("curated_claims") or []
    merged = curate_comparison_claim_rows(
        state.evidence,
        places,
        existing_rows=[*brief.curated_claims, *filter_rows],
    )
    if not merged:
        return brief
    overall = sum(c.confidence * c.relevance_score for c in merged) / len(merged)
    notes = list(brief.curation_notes or [])
    notes.append(f"comparison per-place curation: {len(merged)} claims across {len(places)} places")
    return brief.model_copy(
        update={
            "target_label": target_label,
            "curated_claims": merged,
            "overall_confidence": round(overall, 3),
            "curation_notes": notes,
        }
    )


def summarize_comparison_claims_for_compose(
    claims: list,
    places: list[str],
    *,
    max_per_place_dim: int = 2,
    value_max_len: int = 220,
) -> list[dict]:
    """Trim comparison curated claims for S8 LLM input (per place × dimension)."""
    if not claims or not places:
        return []

    def _as_dict(item) -> dict:
        if isinstance(item, dict):
            return item
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return {}

    buckets: dict[tuple[str, str], list[dict]] = {}
    for raw in claims:
        row = _as_dict(raw)
        claim_place = str(row.get("place_name") or "").strip()
        dim = str(row.get("claim_type") or "").strip()
        value = str(row.get("value") or "").strip()
        if not value:
            continue
        matched_place = ""
        for target in places:
            if claim_place and places_match(target, claim_place):
                matched_place = target
                break
            if target in value or (claim_place and claim_place in target):
                matched_place = target
                break
        if not matched_place:
            continue
        key = (matched_place, dim)
        buckets.setdefault(key, []).append(row)

    out: list[dict] = []
    for place in places:
        for dim in _COMPARISON_DIMENSIONS:
            rows = sorted(
                buckets.get((place, dim), []),
                key=lambda r: (float(r.get("relevance_score", 0)), float(r.get("confidence", 0))),
                reverse=True,
            )
            for row in rows[:max_per_place_dim]:
                trimmed = dict(row)
                trimmed["value"] = str(trimmed.get("value", ""))[:value_max_len]
                out.append(trimmed)
    return out


def comparison_places_from_state(state: TravelAgentState) -> list[str]:
    frame = state.semantic_frame
    if frame and frame.entities.places:
        return list(frame.entities.places)
    goal = state.user_goal
    if goal and goal.place_candidates:
        return list(goal.place_candidates)
    return []
