"""S8: present unresolved place ambiguity with per-candidate evidence and guide user choice."""

from __future__ import annotations

import math

from app.orchestrator.claim_search_planner import is_search_miss_value
from app.orchestrator.composition_preflight import has_actionable_claim_decisions
from app.orchestrator.information_need_aliases import (
    is_nearby_need,
    query_text_from_state,
    resolve_nearby_need,
)
from app.orchestrator.nearby_recommendation_policy import (
    format_nearby_clue_text,
    is_nearby_information_need,
    nearby_need_label,
    s8_focus_claim_types_for_needs,
)
from app.orchestrator.nearby_anchor_policy import (
    anchor_place_name,
    same_scenic_area_sub_poi_ambiguity,
)
from app.orchestrator.place_disambiguation_guard import (
    _location_key,
    candidate_display_label,
    extract_place_candidates,
    should_apply_unique_resolution,
)
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.user_query import TravelAgentState
from tools.mcp.adapters.baidu_response_parser import (
    candidates_are_ambiguous,
    gate_tokens_from_user_query,
)

_NEARBY_ASSIGNABLE_CLAIMS = frozenset(
    {
        ClaimType.FOOD.value,
        ClaimType.LODGING.value,
        ClaimType.GENERAL_FACT.value,
        ClaimType.RATING_CANDIDATE.value,
        ClaimType.ADDRESS.value,
    }
)
_NEARBY_PROXIMITY_MAX_M = 2500.0

_INFORMATION_NEED_LABELS: dict[str, str] = {
    "elevation": "海拔",
    "ticket_price": "门票价格",
    "opening_hours": "开放时间",
    "address": "地址",
    "crowd": "人流情况",
    "reservation": "预约要求",
    "transit": "交通",
    "weather": "天气",
    "entity_resolution": "地点定位",
    "nearby_food": "周边美食",
    "nearby_poi": "周边地点",
    "nearby_hotel": "周边住宿",
    "nearby_toilet": "周边厕所",
    "nearby_parking": "周边停车",
    "nearby_rest_area": "周边休息点",
    "nearby_station": "周边交通站点",
}


def resolve_disambiguation_candidates(state: TravelAgentState) -> list[dict]:
    from_evidence = extract_place_candidates(list(state.evidence or []))
    if from_evidence:
        return from_evidence[:5]
    structured = state.structured_result or {}
    stored = structured.get("place_disambiguation_candidates") or []
    return [c for c in stored if isinstance(c, dict)][:5]


def _required_information_needs(state: TravelAgentState) -> set[str]:
    text = query_text_from_state(state)
    needs: set[str] = set()
    frame = state.semantic_frame
    if frame and frame.information_needs:
        for n in frame.information_needs:
            if is_nearby_need(n):
                needs.add(resolve_nearby_need(n, text=text))
            else:
                needs.add(n)
    contract = state.response_contract
    if contract:
        for req in contract.claim_requirements:
            if req.priority == "required":
                if is_nearby_need(req.claim_type):
                    needs.add(resolve_nearby_need(req.claim_type, text=text))
                else:
                    needs.add(req.claim_type)
    return needs


def _frame_pins_single_candidate(state: TravelAgentState, candidates: list[dict]) -> bool:
    frame = state.semantic_frame
    if not frame or not frame.entities:
        return False
    city = (frame.entities.city or "").strip()
    region = (frame.entities.region or "").strip()
    if not city and not region:
        return False
    matches: list[dict] = []
    for candidate in candidates:
        ccity = (candidate.get("city") or "").strip()
        cprov = (candidate.get("province") or "").strip()
        if city and (city == ccity or city in ccity or ccity in city):
            matches.append(candidate)
        elif region and (region == cprov or region in cprov or cprov in region):
            matches.append(candidate)
    return len(matches) == 1


def _anchor_place_name(state: TravelAgentState) -> str:
    return anchor_place_name(state)


def _same_scenic_area_sub_poi_ambiguity(candidates: list[dict], anchor_place: str) -> bool:
    return same_scenic_area_sub_poi_ambiguity(candidates, anchor_place)


def _requires_place_disambiguation_despite_adoption(state: TravelAgentState) -> bool:
    """Nearby / same-area queries: keep disambiguation even when S7 adopted partial POI evidence."""
    required = _required_information_needs(state)
    if not any(is_nearby_information_need(n) for n in required):
        return False
    candidates = resolve_disambiguation_candidates(state)
    return _same_scenic_area_sub_poi_ambiguity(candidates, _anchor_place_name(state))


def _has_adoptable_required_answer(state: TravelAgentState) -> bool:
    report = state.evidence_decision_report
    if not report:
        return False
    required = _required_information_needs(state)
    actionable = frozenset({"adopt", "adopt_with_limitation", "candidate_only"})
    for decision in report.claim_decisions:
        if required and decision.claim_type not in required:
            continue
        if decision.adoption in actionable:
            if decision.adoption == "candidate_only" and not has_actionable_claim_decisions(state):
                continue
            return True
    return False


def should_present_place_disambiguation_at_s8(state: TravelAgentState) -> bool:
    """True when post-disambiguation we still cannot adopt a single place-specific answer."""
    candidates = resolve_disambiguation_candidates(state)
    if len(candidates) < 2 or not candidates_are_ambiguous(candidates):
        return False
    if should_apply_unique_resolution(candidates) and _frame_pins_single_candidate(state, candidates):
        return False
    if _requires_place_disambiguation_despite_adoption(state):
        return True
    if _has_adoptable_required_answer(state):
        return False
    return True


def user_question_label(state: TravelAgentState) -> str:
    required = _required_information_needs(state)
    nearby = [n for n in required if is_nearby_information_need(n)]
    if len(nearby) > 1:
        return "、".join(nearby_need_label(n) for n in nearby)
    for key in (
        "nearby_food",
        "nearby_toilet",
        "nearby_parking",
        "nearby_hotel",
        "nearby_poi",
        "elevation",
        "ticket_price",
        "opening_hours",
        "crowd",
        "address",
    ):
        if key in required:
            return _INFORMATION_NEED_LABELS.get(key, nearby_need_label(key))
    if required:
        first = next(iter(required))
        if is_nearby_information_need(first):
            return nearby_need_label(first)
        return _INFORMATION_NEED_LABELS.get(first, first)
    return "您关心的问题"


def _focus_claim_types(state: TravelAgentState) -> set[str] | None:
    required = _required_information_needs(state)
    nearby_types = s8_focus_claim_types_for_needs(required)
    if nearby_types:
        return nearby_types
    if required:
        return set(required)
    return None


def _candidate_coords(candidate: dict) -> dict[str, float] | None:
    lat, lng = candidate.get("latitude"), candidate.get("longitude")
    if lat is None or lng is None:
        return None
    return {"latitude": float(lat), "longitude": float(lng)}


def _coords_from_nearby_claim(claim) -> dict[str, float] | None:
    nv = claim.normalized_value
    if isinstance(nv, dict):
        lat, lng = nv.get("latitude"), nv.get("longitude")
        if lat is not None and lng is not None:
            return {"latitude": float(lat), "longitude": float(lng)}
    return None


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _candidate_matches_user_gate(candidate: dict, user_query: str) -> bool:
    tokens = gate_tokens_from_user_query(user_query)
    if not tokens:
        return False
    label = f"{candidate.get('name') or ''} {candidate.get('address') or ''}"
    return any(token in label for token in tokens)


def _loose_anchor_match(evidence: Evidence, candidate: dict, anchor_place: str) -> bool:
    anchor = (anchor_place or "").strip()
    if not anchor or len(anchor) < 2:
        return False
    cand_label = f"{candidate.get('name') or ''} {candidate.get('address') or ''}"
    if anchor not in cand_label:
        return False
    haystack = " ".join(
        filter(
            None,
            [
                evidence.place_name or "",
                str(evidence.city or ""),
                *(str(c.value) for c in evidence.claims if c.claim_type != ClaimType.PLACE_CANDIDATES),
            ],
        )
    )
    return anchor in haystack


def _nearest_candidate_index(
    coords: dict[str, float],
    candidates: list[dict],
    *,
    max_m: float = _NEARBY_PROXIMITY_MAX_M,
) -> int | None:
    best_idx: int | None = None
    best_dist = float("inf")
    lat1, lng1 = coords["latitude"], coords["longitude"]
    for idx, candidate in enumerate(candidates):
        cc = _candidate_coords(candidate)
        if not cc:
            continue
        dist = _haversine_m(lat1, lng1, cc["latitude"], cc["longitude"])
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    if best_idx is not None and best_dist <= max_m:
        return best_idx
    return None


def _assign_proximity_nearby_clues(
    state: TravelAgentState,
    candidates: list[dict],
    options: list[dict],
    *,
    focus_claim_types: set[str] | None,
    assigned_evidence_ids: set[str],
) -> None:
    """Attach nearby POI clues to the nearest gate/anchor candidate by coordinates."""
    question = user_question_label(state)
    anchor = _anchor_place_name(state)
    user_query = state.raw_user_query or ""
    gate_indices = [i for i, c in enumerate(candidates) if _candidate_matches_user_gate(c, user_query)]

    for ev in state.evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if ev.evidence_id in assigned_evidence_ids:
            continue
        if any(_evidence_matches_candidate(ev, c) for c in candidates):
            continue
        for claim in ev.claims:
            if claim.claim_type == ClaimType.PLACE_CANDIDATES:
                continue
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if focus_claim_types and ct not in focus_claim_types:
                continue
            if ct not in _NEARBY_ASSIGNABLE_CLAIMS:
                continue
            text, eid = _format_claim_clue(ev, claim, question_label=question)
            if not text:
                continue
            target_idx: int | None = None
            coords = _coords_from_nearby_claim(claim)
            if coords:
                if gate_indices:
                    gate_dists = [
                        (_haversine_m(coords["latitude"], coords["longitude"], _candidate_coords(candidates[i])["latitude"], _candidate_coords(candidates[i])["longitude"]), i)
                        for i in gate_indices
                        if _candidate_coords(candidates[i])
                    ]
                    if gate_dists:
                        gate_dists.sort()
                        if gate_dists[0][0] <= _NEARBY_PROXIMITY_MAX_M:
                            target_idx = gate_dists[0][1]
                if target_idx is None:
                    target_idx = _nearest_candidate_index(coords, candidates)
            if target_idx is None:
                for idx, candidate in enumerate(candidates):
                    if _loose_anchor_match(ev, candidate, anchor):
                        target_idx = idx
                        break
            if target_idx is None:
                continue
            opt = options[target_idx]
            clues = list(opt.get("evidence_clues") or [])
            if text in clues:
                continue
            clues.append(text)
            opt["evidence_clues"] = clues[:8]
            opt["has_clues_for_question"] = True
            cited = list(opt.get("cited_evidence_ids") or [])
            if eid and eid not in cited:
                cited.append(eid)
            opt["cited_evidence_ids"] = cited
            if ev.evidence_id:
                assigned_evidence_ids.add(ev.evidence_id)


def _candidate_tokens(candidate: dict) -> list[str]:
    tokens: list[str] = []
    for key in ("province", "city", "name", "address"):
        value = (candidate.get(key) or "").strip()
        if value and len(value) >= 2:
            tokens.append(value)
    return tokens


def _evidence_matches_candidate(evidence: Evidence, candidate: dict) -> bool:
    if any(c.claim_type == ClaimType.PLACE_CANDIDATES for c in evidence.claims):
        return False
    cand_key = _location_key(candidate)
    for claim in evidence.claims:
        nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
        if nv.get("anchor_location_key") and nv.get("anchor_location_key") == cand_key:
            return True
    tokens = _candidate_tokens(candidate)
    if not tokens:
        return False
    haystack = " ".join(
        filter(
            None,
            [
                evidence.place_name or "",
                evidence.city or "",
                evidence.country or "",
            ],
        )
    )
    for claim in evidence.claims:
        if is_search_miss_value(str(claim.value)):
            continue
        haystack += f" {claim.value}"
    cand_name = (candidate.get("name") or "").strip()
    for gate in ("和平门", "解放门", "玄武门", "情侣园", "太平门", "翠洲门", "北门"):
        if gate in cand_name and gate in haystack:
            return True
    return any(token in haystack for token in tokens)


def _format_claim_clue(evidence: Evidence, claim, *, question_label: str = "") -> tuple[str, str]:
    value = str(claim.value).strip()
    if not value or is_search_miss_value(value):
        return "", ""
    nearby_text = format_nearby_clue_text(claim, question_label=question_label)
    if nearby_text:
        conf = f"{float(claim.confidence):.0%}" if claim.confidence is not None else "—"
        source = evidence.source_name or "检索来源"
        return f"{nearby_text}（来源：{source}，置信度 {conf}）", evidence.evidence_id
    label = _INFORMATION_NEED_LABELS.get(claim.claim_type.value, claim.claim_type.value)
    conf = f"{float(claim.confidence):.0%}" if claim.confidence is not None else "—"
    source = evidence.source_name or "检索来源"
    text = f"{label}：{value}（来源：{source}，置信度 {conf}）"
    return text, evidence.evidence_id


def collect_evidence_clues_for_candidate(
    state: TravelAgentState,
    candidate: dict,
    *,
    focus_claim_types: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    clues: list[str] = []
    cited: list[str] = []
    seen: set[str] = set()
    question = user_question_label(state)
    for ev in state.evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if not _evidence_matches_candidate(ev, candidate):
            continue
        for claim in ev.claims:
            if claim.claim_type == ClaimType.PLACE_CANDIDATES:
                continue
            if focus_claim_types and claim.claim_type.value not in focus_claim_types:
                continue
            text, eid = _format_claim_clue(ev, claim, question_label=question)
            if not text or text in seen:
                continue
            seen.add(text)
            clues.append(text)
            if eid and eid not in cited:
                cited.append(eid)
    return clues[:6], cited


def collect_unassigned_evidence_clues(
    state: TravelAgentState,
    candidates: list[dict],
    *,
    focus_claim_types: set[str] | None = None,
    skip_evidence_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    clues: list[str] = []
    cited: list[str] = []
    seen: set[str] = set()
    question = user_question_label(state)
    skipped = skip_evidence_ids or set()
    for ev in state.evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if ev.evidence_id in skipped:
            continue
        if any(_evidence_matches_candidate(ev, c) for c in candidates):
            continue
        for claim in ev.claims:
            if claim.claim_type == ClaimType.PLACE_CANDIDATES:
                continue
            if focus_claim_types and claim.claim_type.value not in focus_claim_types:
                continue
            text, eid = _format_claim_clue(ev, claim, question_label=question)
            if not text or text in seen:
                continue
            seen.add(text)
            clues.append(text)
            if eid and eid not in cited:
                cited.append(eid)
    return clues[:8], cited


def build_disambiguation_options(state: TravelAgentState) -> dict:
    candidates = resolve_disambiguation_candidates(state)
    focus = _focus_claim_types(state)
    question = user_question_label(state)
    place_name = _anchor_place_name(state) or ""

    options: list[dict] = []
    all_cited: list[str] = []
    assigned_evidence_ids: set[str] = set()
    for idx, candidate in enumerate(candidates[:5], start=1):
        display = candidate_display_label(candidate)
        clues, cited = collect_evidence_clues_for_candidate(state, candidate, focus_claim_types=focus)
        for eid in cited:
            assigned_evidence_ids.add(eid)
        all_cited.extend(eid for eid in cited if eid not in all_cited)
        coord = None
        lat, lng = candidate.get("latitude"), candidate.get("longitude")
        if lat is not None and lng is not None:
            coord = f"{lat}, {lng}"
        options.append(
            {
                "index": idx,
                "display_label": display,
                "location_key": _location_key(candidate),
                "province": (candidate.get("province") or "").strip(),
                "city": (candidate.get("city") or "").strip(),
                "name": (candidate.get("name") or place_name or "").strip(),
                "address": (candidate.get("address") or "").strip(),
                "coordinates": coord,
                "evidence_clues": clues,
                "cited_evidence_ids": cited,
                "question_label": question,
                "has_clues_for_question": bool(clues),
            }
        )

    _assign_proximity_nearby_clues(
        state,
        candidates[:5],
        options,
        focus_claim_types=focus,
        assigned_evidence_ids=assigned_evidence_ids,
    )
    for opt in options:
        if opt.get("evidence_clues"):
            opt["has_clues_for_question"] = True
        for eid in opt.get("cited_evidence_ids") or []:
            all_cited.extend(x for x in [eid] if x not in all_cited)

    shared_clues, shared_cited = collect_unassigned_evidence_clues(
        state,
        candidates,
        focus_claim_types=focus,
        skip_evidence_ids=assigned_evidence_ids,
    )
    shared_clues = [c for c in shared_clues if c not in {clue for opt in options for clue in (opt.get("evidence_clues") or [])}]
    if shared_clues:
        all_cited.extend(eid for eid in shared_cited if eid not in all_cited)

    return {
        "place_name": place_name,
        "question_label": question,
        "options": options,
        "shared_clues": shared_clues,
        "cited_evidence_ids": all_cited,
        "required_information_needs": sorted(focus) if focus else [],
    }


def build_disambiguation_presentation(state: TravelAgentState) -> dict:
    """Structured bundle for S8 composer (LLM + deterministic fallback)."""
    presentation = build_disambiguation_options(state)
    report = state.evidence_decision_report
    adoption_notes: list[str] = []
    if report:
        for decision in report.claim_decisions:
            if decision.claim_type in _required_information_needs(state):
                adoption_notes.append(
                    f"{decision.claim_type}: {decision.adoption} — {decision.reason or '无法唯一采纳'}"
                )
    presentation["adoption_notes"] = adoption_notes
    presentation["selection_prompt"] = (
        "请回复序号（如「1」）或补充更具体的省/市/景区名称，以便继续查询。"
    )
    return presentation


def prepare_place_disambiguation_compose_context(
    state: TravelAgentState,
    compose_kwargs: dict,
) -> dict:
    presentation = build_disambiguation_presentation(state)
    place_name = presentation.get("place_name") or compose_kwargs.get("target_label") or "目的地"
    return {
        **compose_kwargs,
        "compose_mode": "place_disambiguation",
        "target_label": place_name,
        "disambiguation_presentation": presentation,
    }


def build_disambiguation_draft(state: TravelAgentState, presentation: dict | None = None) -> FinalAnswerDraft:
    pres = presentation or build_disambiguation_presentation(state)
    limitations = list(state.limitations)
    return _draft_from_presentation(pres, limitations)


def build_disambiguation_draft_from_bundle(bundle: dict) -> FinalAnswerDraft:
    pres = bundle.get("disambiguation_presentation") or {}
    limitations = list(bundle.get("limitations") or [])
    return _draft_from_presentation(pres, limitations)


def _draft_from_presentation(pres: dict, limitations: list[str]) -> FinalAnswerDraft:
    place_name = pres.get("place_name") or "该地点"
    question = pres.get("question_label") or "您关心的问题"
    options = pres.get("options") or []
    sections: list[FinalAnswerSection] = []

    shared = pres.get("shared_clues") or []
    has_shared_for_question = bool(shared)
    for opt in options:
        bullets: list[str] = []
        if opt.get("address"):
            bullets.append(f"地址：{opt['address']}")
        elif opt.get("province") or opt.get("city"):
            bullets.append(
                "行政区："
                + " ".join(p for p in (opt.get("province"), opt.get("city")) if p)
            )
        if opt.get("coordinates"):
            bullets.append(f"坐标：{opt['coordinates']}")
        for clue in opt.get("evidence_clues") or []:
            bullets.append(clue)
        if not opt.get("has_clues_for_question"):
            if has_shared_for_question:
                bullets.append(
                    f"关于{question}：本候选暂无直接匹配证据，可参考下方「周边检索线索（未能精确归属）」。"
                )
            else:
                bullets.append(f"关于{question}：本轮检索未找到可采纳的相关证据。")
        title = f"{opt.get('index', len(sections) + 1)}. {opt.get('display_label', place_name)}"
        sections.append(FinalAnswerSection(title=title, bullets=bullets))

    if shared:
        sections.append(
            FinalAnswerSection(
                title="周边检索线索（未能精确归属到单一候选）",
                bullets=shared,
            )
        )

    selection = pres.get("selection_prompt") or "请回复序号或补充省/市信息。"
    headline = f"{place_name}有多个同名地点，请先确认您指的是哪一个"
    conclusion = (
        f"在无法唯一确定地点前，暂不能给出关于{question}的确定结论。"
        f"下列为各候选地点及本轮检索到的信息。{selection}"
    )

    merged_limits = list(limitations)
    for note in pres.get("adoption_notes") or []:
        if note not in merged_limits:
            merged_limits.append(note)
    if "place_disambiguation" not in merged_limits:
        merged_limits.append("place_disambiguation")

    cited = list(pres.get("cited_evidence_ids") or [])
    for opt in options:
        for eid in opt.get("cited_evidence_ids") or []:
            if eid not in cited:
                cited.append(eid)

    draft = FinalAnswerDraft(
        headline=headline,
        conclusion=conclusion,
        sections=sections,
        limitations=merged_limits,
        cited_evidence_ids=cited,
        compose_mode="place_disambiguation",
    )
    draft.answer_text = draft.render_text().strip()
    return draft
