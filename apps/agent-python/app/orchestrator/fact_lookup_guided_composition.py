"""S8 fact_lookup_guided: lead with hard-fact conclusion + sourced details."""

from __future__ import annotations

from app.orchestrator.fact_lookup_anchor_policy import place_scope_note, resolved_place_label
from app.orchestrator.fact_lookup_policy import (
    collect_fact_clues,
    fact_need_label,
    has_official_fact_evidence,
    is_geographic_fact_need,
    primary_fact_need_from_state,
)
from app.orchestrator.place_disambiguation_composition import (
    build_disambiguation_presentation,
    user_question_label,
)
from app.orchestrator.place_disambiguation_guard import extract_place_candidates
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.user_query import TravelAgentState


def build_fact_lookup_presentation(state: TravelAgentState) -> dict:
    need = primary_fact_need_from_state(state)
    label = fact_need_label(need)
    clues = collect_fact_clues(state)
    place = _place_name(state)
    candidates = extract_place_candidates(list(state.evidence or []))
    official = has_official_fact_evidence(list(state.evidence or []), need)
    scope_note = place_scope_note(state, need)

    disambiguation = None
    if len(candidates) >= 2:
        disambiguation = build_disambiguation_presentation(state)

    compose_instructions = [
        f"先给出**结论**：直接回答{label}（有证据则写数值/时段，无则写「无法确认」）。",
        "仅使用 fact_clues 与 cited evidence；**禁止**用模型常识补全未出现在证据中的数值。",
        "逐条列出 fact_clues，每条附 source_name 与置信度；官方来源优先标注。",
        "禁止编造票价/开放时间/海拔；不得把攻略帖当官方终证。",
        "若证据不足或互相矛盾，明确说明缺口，不要写「常见官方引用」类常识。",
        "末尾写 limitations：检索日期、是否官方、缺口说明。",
    ]
    if is_geographic_fact_need(need):
        compose_instructions.append(
            "地理数值类问题：只采纳证据中带明确米制/数值的陈述；景区面积、经纬度、局部海拔不等于用户所问主峰高度。"
        )
    if scope_note:
        compose_instructions.insert(1, f"地点范围：{scope_note}")

    return {
        "place_name": place,
        "question_label": user_question_label(state),
        "primary_fact_need": need,
        "fact_need_label": label,
        "fact_clues": clues,
        "fact_clue_count": len(clues),
        "has_official_evidence": official,
        "place_scope_note": scope_note,
        "disambiguation_presentation": disambiguation,
        "candidate_count": len(candidates),
        "compose_instructions": compose_instructions,
    }


def _place_name(state: TravelAgentState) -> str:
    return resolved_place_label(state) or "目的地"


def prepare_fact_lookup_guided_compose_context(state: TravelAgentState, compose_kwargs: dict) -> dict:
    presentation = build_fact_lookup_presentation(state)
    place = presentation.get("place_name") or compose_kwargs.get("target_label") or "目的地"
    return {
        **compose_kwargs,
        "compose_mode": "fact_lookup_guided",
        "target_label": place,
        "fact_lookup_presentation": presentation,
        "has_actionable_evidence": bool(presentation.get("fact_clues")),
    }


def build_fact_lookup_draft(
    state: TravelAgentState,
    presentation: dict | None = None,
) -> FinalAnswerDraft:
    pres = presentation or build_fact_lookup_presentation(state)
    place = pres.get("place_name") or "该地点"
    label = pres.get("fact_need_label") or "关键事实"
    need = pres.get("primary_fact_need") or "general_fact"
    clues = pres.get("fact_clues") or []
    official = pres.get("has_official_evidence")
    limitations = list(state.limitations or [])
    cited: list[str] = []

    sections: list[FinalAnswerSection] = []
    if clues:
        bullets = []
        for item in clues:
            val = item.get("text") or ""
            src = item.get("source_name") or "证据"
            conf = int(float(item.get("confidence") or 0.5) * 100)
            tag = "官方" if item.get("official") else "第三方"
            bullets.append(f"{val}（来源：{src}，{tag}，置信度 {conf}%）")
            eid = item.get("evidence_id")
            if eid and eid not in cited:
                cited.append(eid)
        headline = f"根据当前证据，{place}{label}如下（共 {len(clues)} 条）。"
        if not official:
            headline += " 尚未检索到明确官方口径，以下仅供核对参考。"
        sections.append(FinalAnswerSection(title=f"{place}{label}", bullets=[headline, *bullets]))
    else:
        sections.append(
            FinalAnswerSection(
                title=f"{place}{label}",
                bullets=[
                    f"本轮检索**无法确认**{place}的{label}。",
                    "建议通过景区/官方渠道或权威资料进一步核实。",
                ],
            )
        )
        limitations.append(f"缺少可采纳的{label}结构化证据。")

    if not official and clues:
        limitations.append(f"{label}暂无官方来源证据，请勿将第三方信息当作最终硬事实。")

    disambiguation = pres.get("disambiguation_presentation")
    options = [
        o for o in (disambiguation.get("options") or []) if (o.get("label") or "").strip()
    ] if disambiguation else []
    if options:
        opt_lines = [f"{o.get('index', i+1)}. {o.get('label', '')}" for i, o in enumerate(options[:6])]
        sections.append(
            FinalAnswerSection(
                title="地点消歧（可选）",
                bullets=[
                    "若您所指非以下默认地点，请回复序号以便按正确景区再查：",
                    *opt_lines,
                ],
            )
        )

    sections.append(
        FinalAnswerSection(
            title="说明",
            bullets=[
                "以上仅基于本轮工具证据，不以模型常识补全硬事实。",
                "价格、开放政策与地理数据可能调整，出行前请以官方最新公告为准。",
            ],
        )
    )

    return FinalAnswerDraft(
        title=f"{place}{label}",
        sections=sections,
        cited_evidence_ids=cited,
        limitations=limitations,
        compose_mode="fact_lookup_guided",
        metadata={"primary_fact_need": need},
    )
