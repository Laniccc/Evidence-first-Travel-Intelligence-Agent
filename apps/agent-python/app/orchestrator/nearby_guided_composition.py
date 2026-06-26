"""S8 nearby_guided: area-level nearby POI from evidence + optional sub-POI disambiguation."""

from __future__ import annotations

from app.orchestrator.claim_search_planner import is_search_miss_value
from app.orchestrator.information_need_aliases import (
    all_nearby_needs_from_state,
    primary_nearby_need_from_state,
    resolve_nearby_need,
)
from app.orchestrator.nearby_recommendation_policy import (
    actionable_claim_types_for_need,
    extract_poi_name_from_claim_value,
    format_nearby_clue_text,
    is_adoptable_nearby_poi,
    nearby_need_label,
)
from app.orchestrator.nearby_enrichment_policy import build_poi_reputation_index, lookup_poi_reputation
from app.orchestrator.nearby_task_orchestration import is_nearby_recommendation_task
from app.orchestrator.place_disambiguation_composition import (
    build_disambiguation_presentation,
    user_question_label,
)
from app.orchestrator.place_disambiguation_guard import extract_place_candidates
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.user_query import TravelAgentState


def _required_nearby_needs(state: TravelAgentState) -> set[str]:
    return set(all_nearby_needs_from_state(state))


def _claim_need(claim, *, fallback: str) -> str:
    nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
    raw = nv.get("information_need") or nv.get("nearby_category") or fallback
    return resolve_nearby_need(str(raw))


def collect_area_nearby_clues_by_need(state: TravelAgentState, *, limit: int = 12) -> dict[str, list[dict]]:
    """Nearby POI clues grouped by information_need."""
    needs = _required_nearby_needs(state)
    anchor = anchor_place_name_from_state(state)
    by_need: dict[str, list[dict]] = {n: [] for n in needs}
    seen: dict[str, set[str]] = {n: set() for n in needs}
    reputation_index = build_poi_reputation_index(list(state.evidence or []))

    for ev in state.evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            if claim.claim_type == ClaimType.PLACE_CANDIDATES:
                continue
            claim_need = _claim_need(claim, fallback=primary_nearby_need_from_state(state))
            if claim_need not in by_need:
                by_need[claim_need] = []
                seen[claim_need] = set()
            focus = actionable_claim_types_for_need(claim_need)
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if focus and ct not in focus:
                continue
            val = str(claim.value or "").strip()
            if not val or is_search_miss_value(val):
                continue
            poi_name = extract_poi_name_from_claim_value(val)
            nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
            if not is_adoptable_nearby_poi(
                poi_name,
                claim_need,
                anchor_place=anchor,
                poi_tag=nv.get("baidu_item_tag") or nv.get("tag") or nv.get("type"),
                search_tag=nv.get("search_tag"),
            ):
                continue
            section_label = nearby_need_label(claim_need)
            rep = lookup_poi_reputation(
                reputation_index,
                uid=str(nv.get("uid") or "") or None,
                name=poi_name,
            )
            text = format_nearby_clue_text(claim, question_label=section_label, reputation=rep)
            if not text or text in seen[claim_need]:
                continue
            seen[claim_need].add(text)
            conf = float(getattr(claim, "confidence", None) or ev.confidence or 0.5)
            by_need[claim_need].append(
                {
                    "text": text,
                    "claim_type": ct,
                    "information_need": claim_need,
                    "evidence_id": ev.evidence_id,
                    "source_name": ev.source_name or "",
                    "confidence": conf,
                }
            )
    for need in list(by_need.keys()):
        by_need[need] = by_need[need][:limit]
    return by_need


def collect_area_nearby_clues(state: TravelAgentState, *, limit: int = 12) -> list[dict]:
    """All nearby POI clues in the scenic area (not gated by anchor_location_key)."""
    by_need = collect_area_nearby_clues_by_need(state, limit=limit)
    flat: list[dict] = []
    for clues in by_need.values():
        flat.extend(clues)
        if len(flat) >= limit:
            return flat[:limit]
    return flat


def build_nearby_guided_presentation(state: TravelAgentState) -> dict:
    place_name = anchor_place_name_from_state(state)
    all_needs = all_nearby_needs_from_state(state)
    primary_need = all_needs[0] if all_needs else "nearby_poi"
    clues_by_need = collect_area_nearby_clues_by_need(state)
    area_clues = collect_area_nearby_clues(state)
    candidates = extract_place_candidates(list(state.evidence or []))

    if len(all_needs) > 1:
        question = "、".join(nearby_need_label(n) for n in all_needs)
    else:
        question = user_question_label(state)

    disambiguation = None
    if len(candidates) >= 2:
        disambiguation = build_disambiguation_presentation(state)

    default_note = ""
    if len(candidates) >= 2 and place_name:
        default_note = (
            f"未特别说明时，以下结果按「{place_name}」所在片区汇总，"
            "不区分具体门点/出入口；若您从不同入口进入，步行距离可能略有差异。"
        )

    compose_instructions = [
        f"先给出可执行的片区级{question}推荐（逐条列出 area_nearby_clues，附来源与置信度）。",
        "不要因门点未消歧就拒绝回答；消歧放在后半段轻量说明。",
        "仅使用 evidence 中的名称与地址，禁止编造评分或主观排名。",
        "若证据条数少，明确写覆盖有限；可建议用户补充城市/入口。",
    ]
    if len(all_needs) > 1:
        compose_instructions.insert(
            0,
            "复合查询：按 area_nearby_clues_by_need 分节输出，每节对应一种需求（如美食、停车场）。",
        )

    return {
        "place_name": place_name,
        "question_label": question,
        "primary_nearby_need": primary_need,
        "all_nearby_needs": all_needs,
        "area_nearby_clues": area_clues,
        "area_nearby_clues_by_need": clues_by_need,
        "area_nearby_count": len(area_clues),
        "default_assumption_note": default_note,
        "disambiguation_presentation": disambiguation,
        "candidate_count": len(candidates),
        "compose_instructions": compose_instructions,
    }


def anchor_place_name_from_state(state: TravelAgentState) -> str:
    from app.orchestrator.nearby_anchor_policy import anchor_place_name

    return anchor_place_name(state) or "目的地"


def prepare_nearby_guided_compose_context(state: TravelAgentState, compose_kwargs: dict) -> dict:
    presentation = build_nearby_guided_presentation(state)
    place = presentation.get("place_name") or compose_kwargs.get("target_label") or "目的地"
    clues = presentation.get("area_nearby_clues") or []
    return {
        **compose_kwargs,
        "compose_mode": "nearby_guided",
        "target_label": place,
        "nearby_guided_presentation": presentation,
        "has_actionable_evidence": bool(clues),
    }


def _item_noun_for_need(need: str) -> str:
    nouns = {
        "nearby_food": "店铺/餐饮",
        "nearby_toilet": "公厕/卫生间",
        "nearby_parking": "停车场",
        "nearby_hotel": "住宿",
        "nearby_pharmacy": "药店",
        "nearby_hospital": "医院/诊所",
        "nearby_atm": "ATM/银行",
        "nearby_gas": "加油站",
        "nearby_charging": "充电站",
        "nearby_station": "交通站点",
        "nearby_library": "图书馆",
        "nearby_supermarket": "超市/便利店",
        "nearby_scenic": "景点/公园",
    }
    return nouns.get(need, "地点/设施")


def _bullets_from_clues(clues: list[dict], cited: list[str]) -> list[str]:
    rec_bullets: list[str] = []
    for item in clues:
        text = item.get("text") or ""
        src = item.get("source_name") or "证据"
        conf = int(float(item.get("confidence") or 0.5) * 100)
        rec_bullets.append(f"{text}（来源：{src}，置信度 {conf}%）")
        eid = item.get("evidence_id")
        if eid and eid not in cited:
            cited.append(eid)
    return rec_bullets


def build_nearby_guided_draft(
    state: TravelAgentState,
    presentation: dict | None = None,
) -> FinalAnswerDraft:
    pres = presentation or build_nearby_guided_presentation(state)
    place = pres.get("place_name") or "该地点"
    question = pres.get("question_label") or "周边推荐"
    all_needs = pres.get("all_nearby_needs") or [pres.get("primary_nearby_need") or "nearby_poi"]
    primary_need = pres.get("primary_nearby_need") or all_needs[0]
    clues_by_need = pres.get("area_nearby_clues_by_need") or {}
    area_clues = pres.get("area_nearby_clues") or []
    limitations = list(state.limitations or [])
    cited: list[str] = []
    sections: list[FinalAnswerSection] = []

    if len(all_needs) > 1 and clues_by_need:
        for need in all_needs:
            need_clues = clues_by_need.get(need) or []
            label = nearby_need_label(need)
            bullets = _bullets_from_clues(need_clues, cited)
            if not bullets:
                bullets = [f"本轮检索暂未获得可采纳的{label}结构化证据。"]
            sections.append(FinalAnswerSection(title=f"{place}片区{label}", bullets=bullets))
    else:
        rec_bullets = _bullets_from_clues(area_clues, cited)
        if not rec_bullets:
            rec_bullets.append(f"本轮检索暂未获得可采纳的{question}结构化证据。")
        sections.append(FinalAnswerSection(title=f"{place}片区{question}", bullets=rec_bullets))

    note = pres.get("default_assumption_note")
    if note:
        sections.append(FinalAnswerSection(title="说明", bullets=[note]))

    dis = pres.get("disambiguation_presentation")
    if dis and (dis.get("options") or []):
        opt_lines: list[str] = []
        for opt in dis.get("options") or []:
            label = opt.get("display_label") or opt.get("name") or ""
            opt_lines.append(f"{opt.get('index', '?')}. {label}")
        if opt_lines:
            sections.append(
                FinalAnswerSection(
                    title="若需按具体入口/门点细化",
                    bullets=opt_lines
                    + ["请回复序号（如「1」）或说明您从哪个门进入，以便按锚点再检索。"],
                )
            )

    item_noun = _item_noun_for_need(str(primary_need))
    headline = f"{place}附近{question.replace('周边', '')}（片区级，基于当前证据）"
    if area_clues:
        conclusion = (
            f"下列{item_noun}线索来自本轮地图检索，覆盖同一步行圈内。"
            f"共 {len(area_clues)} 条可采纳证据。"
        )
    else:
        conclusion = (
            f"尚未检索到可采纳的{question} POI 证据。"
            f"已解析锚点位置，建议按具体出入口补充说明后重新检索。"
        )
    if len(area_clues) < 3 and area_clues:
        conclusion += " 证据较少，建议到场前在地图 App 核实开放状态。"
        limitations.append(f"{question}证据条数有限，未做口碑或质量排序。")
    if not area_clues:
        limitations.append(f"未检索到{question}相关地图 POI，结论受限。")

    return FinalAnswerDraft(
        headline=headline,
        conclusion=conclusion,
        sections=sections,
        limitations=limitations,
        cited_evidence_ids=cited,
        compose_mode="nearby_guided",
        confidence=min(0.85, 0.45 + 0.05 * len(area_clues)) if area_clues else 0.4,
    )


def build_nearby_guided_draft_from_bundle(bundle: dict) -> FinalAnswerDraft:
    pres = bundle.get("nearby_guided_presentation") or {}
    limitations = list(bundle.get("limitations") or [])
    place = pres.get("place_name") or bundle.get("target_label") or "该地点"
    question = pres.get("question_label") or "周边推荐"
    all_needs = pres.get("all_nearby_needs") or [pres.get("primary_nearby_need") or "nearby_poi"]
    primary_need = pres.get("primary_nearby_need") or all_needs[0]
    clues_by_need = pres.get("area_nearby_clues_by_need") or {}
    area_clues = pres.get("area_nearby_clues") or []
    cited: list[str] = []
    sections: list[FinalAnswerSection] = []

    if len(all_needs) > 1 and clues_by_need:
        for need in all_needs:
            need_clues = clues_by_need.get(need) or []
            label = nearby_need_label(need)
            bullets = _bullets_from_clues(need_clues, cited)
            if not bullets:
                bullets = [f"本轮检索暂未获得可采纳的{label}结构化证据。"]
            sections.append(FinalAnswerSection(title=f"{place}片区{label}", bullets=bullets))
    else:
        rec_bullets = _bullets_from_clues(area_clues, cited)
        if not rec_bullets:
            rec_bullets.append(f"本轮检索暂未获得可采纳的{question}结构化证据。")
        sections.append(FinalAnswerSection(title=f"{place}片区{question}", bullets=rec_bullets))

    note = pres.get("default_assumption_note")
    if note:
        sections.append(FinalAnswerSection(title="说明", bullets=[note]))
    headline = f"{place}附近{question.replace('周边', '')}（片区级，基于当前证据）"
    item_noun = _item_noun_for_need(str(primary_need))
    if area_clues:
        conclusion = f"下列{item_noun}线索来自本轮地图检索，共 {len(area_clues)} 条可采纳证据。"
    else:
        conclusion = f"尚未检索到可采纳的{question} POI 证据。"
    return FinalAnswerDraft(
        headline=headline,
        conclusion=conclusion,
        sections=sections,
        limitations=limitations,
        cited_evidence_ids=cited,
        compose_mode="nearby_guided",
        confidence=min(0.85, 0.45 + 0.05 * len(area_clues)) if area_clues else 0.4,
    )
