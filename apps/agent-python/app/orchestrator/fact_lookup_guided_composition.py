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
    peak_table = None
    if is_geographic_fact_need(need):
        from app.orchestrator.peak_elevation_extraction import extract_peak_elevation_table

        structured = state.structured_result or {}
        if structured.get("peak_elevation_table"):
            peak_table = structured["peak_elevation_table"]
        else:
            peak_table = extract_peak_elevation_table(
                list(state.evidence or []), place_name=place
            ).model_dump()

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
    if need == "ticket_price":
        from app.orchestrator.ticket_product_policy import ensure_ticket_product_context

        product_ctx = ensure_ticket_product_context(state)
        compose_instructions.insert(
            1,
            "票价类：先说明是否取得官方票价；若仅有飞猪/携程/TicketLens/点评候选价，"
            "须写「官方票价未确认；平台候选价为 X 元，可能随日期/套餐变化」。"
            "不得把平台价写成官方票价；不要把 gov 首页/百科/知乎攻略列为票价线索。",
        )
        if product_ctx and product_ctx.get("ticket_product") == "boat_ticket":
            compose_instructions.insert(
                2,
                "游船/船票类：用户问的是船票而非景区大门票。若无票价证据，应写"
                "「未查到游船票价证据」，可注明可能涉及码头/游船服务点（如双湖游船），"
                "不要要求用户在同一景区内多个 POI 之间做地点消歧；"
                "不要把世界杯/联赛/住宿预算等无关搜索命中列为线索，应概括为「已排除无关页面」。",
            )
        compose_instructions.append(
            "若 official_source_discovery 找到政府/景区背景页但 supports_claim_types 不含 ticket_price "
            "或 has_ticket_info=false，应写「已找到官方背景页，但该页不含票价，不能确认官方票价」，"
            "不得将其列为票价线索。"
        )
    if is_geographic_fact_need(need):
        compose_instructions.append(
            "地理数值类问题：先说明口径（最高峰/主峰/景区整体），再列具体米数；"
            "若有 peak_elevation_table 则按表格列出各峰海拔；"
            "仅「均逾/超过某范围」时须明确未查到精确米数，不得当作已回答「多少米」。"
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
        "peak_elevation_table": peak_table,
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
    peak_table = pres.get("peak_elevation_table") or {}
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
        peaks = peak_table.get("peaks") or []
        if peaks:
            peak_lines = []
            highest = peak_table.get("highest_peak")
            if highest:
                peak_lines.append(f"最高峰候选：{highest}")
            for row in peaks[:6]:
                name = row.get("peak_name") or "山峰"
                elev = row.get("elevation_m")
                if elev is not None:
                    peak_lines.append(f"- {name}：约 {elev} 米")
            if peak_lines:
                sections.append(
                    FinalAnswerSection(title=f"{place}主峰海拔", bullets=peak_lines)
                )
        elif peak_table.get("value_granularity") == "range_only":
            sections.append(
                FinalAnswerSection(
                    title="海拔精度说明",
                    bullets=[
                        "当前证据仅包含海拔范围描述（如「均逾某高度」），未能确认各主峰的具体米数。",
                        "如需精确数值，建议查阅百科/景区官方地理说明。",
                    ],
                )
            )
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

    from app.orchestrator.ticket_lookup_policy import filter_ticket_price_limitations

    limitations = filter_ticket_price_limitations(limitations, need=need)

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
