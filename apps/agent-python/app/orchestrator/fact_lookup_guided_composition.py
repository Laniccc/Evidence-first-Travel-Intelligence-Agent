"""S8 fact_lookup_guided: lead with hard-fact conclusion + sourced details."""

from __future__ import annotations

import re

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
from app.orchestrator.ticket_price_audit import rank_ticket_fact


_TICKET_PRODUCT_LABELS = {
    "entrance_ticket": "大门票/成人票",
    "ticket_price": "门票",
    "boat_ticket": "游船票",
    "shuttle_bus": "景交/区间车票",
    "cable_car": "索道/缆车票",
}


def _format_adopted_ticket_value(value: str) -> str:
    text = str(value or "").strip()
    match = re.search(
        r"\b(?P<product>entrance_ticket|ticket_price|boat_ticket|shuttle_bus|cable_car)\b\s+"
        r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<currency>CNY|RMB|元)?",
        text,
        re.I,
    )
    if not match:
        return text
    product = match.group("product").lower()
    amount = float(match.group("amount"))
    amount_text = f"{amount:g}"
    currency = "元" if (match.group("currency") or "CNY").upper() in {"CNY", "RMB"} else match.group("currency")
    return f"{_TICKET_PRODUCT_LABELS.get(product, product)} {amount_text} {currency}"


def _claim_decision_for_need(state: TravelAgentState, need: str):
    report = state.evidence_decision_report
    if not report:
        return None
    for row in report.claim_decisions:
        if row.claim_type == need:
            return row
    return None


def build_fact_lookup_presentation(state: TravelAgentState) -> dict:
    need = primary_fact_need_from_state(state)
    label = fact_need_label(need, state)
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

    opening_hours_facts = None
    ticket_price_facts = None
    from app.orchestrator.claim_compiler import get_lookup_claims_from_state

    lookup_claims = get_lookup_claims_from_state(state)
    if need in {"ticket_price", "entrance_ticket_price", "boat_ticket_price", "shuttle_bus_ticket_price", "cable_car_ticket_price"}:
        from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_evidence

        primary_claim = next((c for c in lookup_claims if c.claim_type == need), lookup_claims[0] if lookup_claims else None)
        facts = extract_ticket_price_from_evidence(
            list(state.evidence or []),
            claim=primary_claim,
            claim_type=need,
        )
        if facts:
            ticket_price_facts = [{**f.model_dump(), "summary_line": f.summary_line()} for f in facts[:4]]
    ticket_area_policy = None
    if ticket_price_facts and need == "ticket_price":
        from app.orchestrator.ticket_area_policy import build_ticket_area_policy

        ticket_area_policy = build_ticket_area_policy(
            state,
            ticket_price_facts,
            place_name=place,
        )
    if need == "opening_hours":
        from app.orchestrator.opening_hours_extractor import extract_opening_hours_from_evidence

        facts = extract_opening_hours_from_evidence(list(state.evidence or []))
        if facts:
            opening_hours_facts = [
                {**f.model_dump(), "summary_line": f.summary_line()} for f in facts[:4]
            ]

    claim_decision = _claim_decision_for_need(state, need)

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

    if claim_decision:
        level = getattr(claim_decision, "adoption_level", None) or ""
        can_answer = getattr(claim_decision, "can_answer_directly", None)
        must_limit = getattr(claim_decision, "must_show_limitation", None)
        if level == "strong":
            compose_instructions.insert(
                1,
                "S7 判定 adoption_level=strong：可在首句直答，但必须引用官方页或结构化 claim 来源。",
            )
        elif level == "partial":
            compose_instructions.insert(
                1,
                "S7 判定 adoption_level=partial：可给出时段/价格，但必须标注「未完全经官方页面确认」。",
            )
        elif level == "candidate_only":
            compose_instructions.insert(
                1,
                "S7 判定 adoption_level=candidate_only：不得写成定论；须写「第三方/搜索摘要候选，官方未确认」。",
            )
        elif level in {"no_evidence", "rejected", "weak"}:
            compose_instructions.insert(
                1,
                "S7 判定证据不足：首句必须写「无法确认」或等价表述，禁止编造数值。",
            )
        if can_answer is False:
            compose_instructions.append("can_answer_directly=false：不得以肯定句给出未证实数值。")
        if must_limit:
            compose_instructions.append("must_show_limitation=true：limitations 段必须说明证据缺口或仅候选来源。")
        if need == "opening_hours" and opening_hours_facts:
            compose_instructions.append(
                "优先使用 opening_hours_facts 结构化时段；按其 evidence_strength 标注强弱，不得升格为官方终证。"
            )

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
        "opening_hours_facts": opening_hours_facts,
        "ticket_price_facts": ticket_price_facts,
        "ticket_area_policy": ticket_area_policy,
        "lookup_claims": [c.model_dump() for c in lookup_claims],
        "claim_decision": claim_decision.model_dump() if claim_decision else None,
        "compose_instructions": compose_instructions,
    }


def _place_name(state: TravelAgentState) -> str:
    return resolved_place_label(state) or "目的地"


def _rank_ticket_price_facts(rows: list[dict], *, claim_type: str | None = None) -> list[dict]:
    normalized = [r for r in rows if isinstance(r, dict)]
    trusted_sources = {"official", "official_page", "government", "tourism_board", "ticket_platform", "platform"}
    has_structured_price = any(
        str(r.get("source_class") or "").lower() in trusted_sources
        and str(r.get("evidence_strength") or "").lower() in {"strong", "partial"}
        for r in normalized
    )
    if has_structured_price:
        normalized = [
            r
            for r in normalized
            if not (
                str(r.get("source_class") or "").lower() in {"web", "search_snippet"}
                and str(r.get("evidence_strength") or "").lower() == "candidate_only"
            )
        ]

    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for row in sorted(normalized, key=lambda r: rank_ticket_fact(r, claim_type=claim_type)):
        key = (
            str(row.get("ticket_name") or row.get("ticket_product") or ""),
            str(row.get("adult_price") or ""),
            str(row.get("source_url") or row.get("booking_url") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


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
    limitations = list(state.user_visible_limitations or [])
    from app.orchestrator.ticket_lookup_policy import filter_user_visible_limitations

    limitations.extend(filter_user_visible_limitations(list(state.limitations or [])))
    cited: list[str] = []
    claim_decision = pres.get("claim_decision") or {}
    adoption_level = claim_decision.get("adoption_level")
    opening_facts = pres.get("opening_hours_facts") or []
    ticket_facts = _rank_ticket_price_facts(pres.get("ticket_price_facts") or [], claim_type=need)
    ticket_area_policy = pres.get("ticket_area_policy")

    sections: list[FinalAnswerSection] = []
    if opening_facts and need == "opening_hours":
        oh_lines = []
        for row in opening_facts[:3]:
            summary = row.get("open_time") or row.get("close_time")
            line = row.get("summary_line") or (
                f"开放 {row.get('open_time') or '—'}，闭馆 {row.get('close_time') or '—'}"
                if summary
                else ""
            )
            if line:
                strength = row.get("evidence_strength") or "partial"
                oh_lines.append(f"{line}（证据强度：{strength}）")
        if oh_lines:
            title = f"{place}{label}"
            if adoption_level == "partial":
                bullets = [
                    "本轮找到开放时间相关摘要，但未能读取官方页面完全确认，以下仅供参考。",
                    *oh_lines,
                ]
            elif adoption_level == "strong":
                bullets = [f"根据当前证据，{place}{label}如下：", *oh_lines]
            else:
                bullets = [
                    f"本轮未能完全确认{place}{label}；以下为检索摘要中的时间线索。",
                    *oh_lines,
                ]
            sections.append(FinalAnswerSection(title=title, bullets=bullets))
    elif (
        need in {"ticket_price", "entrance_ticket_price", "boat_ticket_price", "shuttle_bus_ticket_price", "cable_car_ticket_price"}
        and claim_decision.get("adopted_value")
        and adoption_level in {"strong", "partial"}
    ):
        adopted = _format_adopted_ticket_value(str(claim_decision.get("adopted_value") or "").strip())
        qualifier = "根据当前证据评审，可采用的票价结论如下。"
        if adoption_level == "partial":
            qualifier = "当前票价结论仍需以官方购票页最终显示为准；证据评审采用值如下。"
        sections.append(
            FinalAnswerSection(
                title=f"{place}{label}",
                bullets=[qualifier, adopted],
            )
        )
    elif ticket_facts and need in {"ticket_price", "entrance_ticket_price", "boat_ticket_price", "shuttle_bus_ticket_price", "cable_car_ticket_price"}:
        if ticket_area_policy:
            policy_lines = [ticket_area_policy.get("guidance") or ""]
            policy_lines.extend(ticket_area_policy.get("free_policy_lines") or [])
            paid_scope = ticket_area_policy.get("paid_scope_lines") or []
            if paid_scope:
                policy_lines.append("另有证据提示部分内部项目可能单独收费：")
                policy_lines.extend(paid_scope)
            sections.append(
                FinalAnswerSection(
                    title=f"{place}是否收费",
                    bullets=[line for line in policy_lines if line],
                )
            )
        ticket_lines = []
        from app.orchestrator.ticket_area_policy import ticket_fact_scope_label

        for row in ticket_facts[:4]:
            line = row.get("summary_line") or ""
            if not line:
                continue
            source_class = row.get("source_class") or "unknown"
            strength = row.get("evidence_strength") or "partial"
            url = row.get("booking_url") or row.get("source_url")
            scope = ticket_fact_scope_label(row, area_policy=ticket_area_policy)
            suffix = f"（来源类型：{source_class}，证据强度：{strength}）"
            if url:
                suffix = f"{suffix} {url}"
            ticket_lines.append(f"{scope}：{line}{suffix}")
        if ticket_lines:
            if ticket_area_policy:
                headline = (
                    f"以下价格只作为{place}内部景点、体验项目或平台商品候选；"
                    f"不能据此认定{place}开放区域整体收费。"
                )
            elif official:
                headline = f"当前证据中包含{place}{label}线索；以下按证据强度列出。"
            else:
                headline = (
                    f"本轮未确认到{place}{label}的官方页面价格；以下为第三方/平台候选价，"
                    "不可写成官方最终票价。"
                )
            if adoption_level == "strong":
                headline = f"根据当前较强证据，{place}{label}如下。"
            sections.append(
                FinalAnswerSection(
                    title=f"{place}{'内部项目/平台候选票价' if ticket_area_policy else label}",
                    bullets=[headline, *ticket_lines],
                )
            )
    elif clues:
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
        if adoption_level == "candidate_only":
            if need == "boat_ticket_price":
                headline = (
                    f"本轮未查到可采纳的{place}游船船票价格；"
                    f"以下第三方摘要仅作参考，不能作为官方结论（共 {len(clues)} 条）。"
                )
            else:
                headline = (
                    f"本轮未查到可采纳的{place}{label}；"
                    f"以下第三方摘要仅作参考，不能作为官方结论（共 {len(clues)} 条）。"
                )
        elif adoption_level == "partial":
            headline = (
                f"本轮找到{place}{label}相关线索，但官方确认不足，以下仅供参考（共 {len(clues)} 条）。"
            )
        elif not official:
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
        no_evidence_bullets = [
            f"本轮检索**无法确认**{place}的{label}。",
        ]
        if adoption_level == "candidate_only":
            adopted = claim_decision.get("adopted_value")
            if adopted:
                no_evidence_bullets = [
                    f"本轮未查到可采纳的{place}{label}。",
                    f"第三方页面摘要提到「{adopted}」，但未能验证是否为当前官方价格，不能作为结论。",
                ]
        from app.orchestrator.ticket_product_policy import ensure_ticket_product_context

        product_ctx = ensure_ticket_product_context(state)
        if product_ctx and product_ctx.get("ticket_product") == "boat_ticket":
            no_evidence_bullets = [
                f"本轮未查到可采纳的{place}「游船/船票」价格证据。",
                "景区门票、区间车票与游船船票是不同票种；本轮未能确认游船票价。",
                "可能涉及景区内游船服务点（如码头、双湖游船），但平台/官方页未返回可用票价。",
            ]
        no_evidence_bullets.append("建议通过景区/官方渠道或授权票务平台进一步核实。")
        sections.append(
            FinalAnswerSection(
                title=f"{place}{label}",
                bullets=no_evidence_bullets,
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
