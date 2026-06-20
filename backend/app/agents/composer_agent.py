from app.catalog.destination_catalog import CULTURAL_SETS
from app.catalog.location_resolver import resolve_start_location
from app.catalog.place_catalog import get_place_catalog
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.itinerary import ItineraryItem, ItineraryPlan
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.response import ComparisonRow, RecommendationResult
from app.schemas.review import ReviewAspectName, ReviewAspectResult
from app.schemas.travel_task import TravelTaskType
from app.schemas.user_query import TravelAgentState, UserGoal


class ComposerAgent:
    @staticmethod
    def _is_zh(text: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in text)

    @staticmethod
    def _level_high(value: float | None, threshold: float = 0.65) -> bool:
        return (value or 0) > threshold

    @staticmethod
    def compose_single(
        place_name: str,
        recommendation: RecommendationResult,
        review: ReviewAspectResult,
        fact_sheet: PlaceFactSheet,
        state: TravelAgentState,
    ) -> str:
        zh = ComposerAgent._is_zh(state.raw_user_query)
        lines = [
            "结论：",
            ComposerAgent._conclusion_text(recommendation, place_name),
            "",
            "适合你吗：",
            *([f"- {p.persona}: {p.fit} — {p.reason}" for p in review.persona_implications] or ["- 请结合同行人体力与偏好判断。"]),
            "",
            "核心依据：",
            *[f"{i + 1}. {r}" for i, r in enumerate(recommendation.main_reasons[:4])],
        ]
        if zh:
            first_timer = (fact_sheet.first_timer_fit or 0) > 0.8
            lines.extend(
                [
                    f"- 文化价值：{'高' if first_timer else '中等'}",
                    f"- 交通：{'较便利' if ComposerAgent._level_high(fact_sheet.transport_convenience, 0.75) else '一般'}",
                    f"- 开放时间：{fact_sheet.official_hours or '证据不足，请出发前确认'}",
                    f"- 适合人群：{', '.join(recommendation.best_for) or '一般游客'}",
                ]
            )
        lines.extend(
            [
                "",
                "建议游玩方式：",
                f"- 建议时间：{recommendation.recommended_time}",
                f"- 推荐时间段：{recommendation.recommended_time}",
                "- 建议控制游玩范围，避免与过多坡道/排队景点同日叠加",
                "- 出发前确认官方开放时间与预约政策",
                "",
                "风险与限制：",
                *[f"- {r}" for r in recommendation.risks],
            ]
        )
        if zh:
            lines.extend(
                [
                    f"- 步行强度：{'偏高' if ComposerAgent._level_high(fact_sheet.walking_intensity) else '中等'}",
                    f"- 拥挤风险：{'较高' if ComposerAgent._level_high(fact_sheet.crowd_risk, 0.7) else '中等'}",
                    f"- 人流：{'高峰时段明显' if ComposerAgent._level_high(fact_sheet.crowd_risk, 0.7) else '可控'}",
                    f"- 预约：{fact_sheet.reservation_policy or '请出发前确认'}",
                ]
            )
        if fact_sheet.ticket_price:
            lines.append(f"- 票价：{fact_sheet.ticket_price}")
        if fact_sheet.weather:
            lines.append(f"- 天气：{fact_sheet.weather}")
        lines.extend(
            [
                *[f"- {l}" for l in state.limitations[:3]],
                "",
                "证据摘要：",
                *ComposerAgent._evidence_summary_lines(state, fact_sheet),
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def compose_advisory(target_label: str, evidence: list[Evidence], state: TravelAgentState) -> str:
        advice_lines: list[str] = []
        for ev in evidence:
            for claim in ev.claims:
                if claim.claim_type in {ClaimType.TRAVEL_ADVICE, ClaimType.SEASONALITY}:
                    advice_lines.append(str(claim.value))

        lines = [
            f"关于 {target_label}：",
            "",
            "结论：",
            advice_lines[0] if advice_lines else "暂无足够建议。",
            "",
            "说明：",
            "- 以下为基于一般旅行常识的低置信度建议，非官方实时信息。",
        ]
        for lim in state.limitations:
            if lim not in lines:
                lines.append(f"- {lim}")
        lines.extend(["", "证据摘要：", *ComposerAgent._evidence_summary_lines(state)])
        return "\n".join(lines)

    @staticmethod
    def compose_crowd_inquiry(
        place_name: str,
        fact_sheet: PlaceFactSheet,
        review: ReviewAspectResult,
        state: TravelAgentState,
    ) -> str:
        crowd = fact_sheet.crowd_risk
        crowd_label = "较高" if ComposerAgent._level_high(crowd, 0.7) else "中等" if crowd is not None else "证据不足"
        queue_aspect = next((a for a in review.aspects if a.aspect == ReviewAspectName.QUEUE_TIME), None)
        queue_note = "评价中提及排队" if queue_aspect else "排队信息有限"

        lines = [
            f"关于 {place_name} 的人流情况：",
            "",
            "重要说明：",
            "- 未接入实时人流/热力数据，以下为基于评价摘要、地图热门程度代理与日期因素的估算，不代表现场实时人数。",
            "",
            "估算结论：",
            f"- 拥挤风险：{crowd_label}" + (f"（代理值 {crowd:.2f}）" if crowd is not None else ""),
            f"- 排队情况：{queue_note}",
        ]
        if fact_sheet.weather:
            lines.append(f"- 天气因素：{fact_sheet.weather}")
        if fact_sheet.reservation_policy:
            lines.append(f"- 预约政策：{fact_sheet.reservation_policy}（可能影响入场人流）")

        crowd_reviews = [a for a in review.aspects if a.aspect in {ReviewAspectName.CROWD_LEVEL, ReviewAspectName.QUEUE_TIME}]
        if crowd_reviews:
            lines.extend(["", "评价维度依据："])
            for a in crowd_reviews[:3]:
                lines.append(f"- {a.aspect.value}: {a.sentiment} (severity={a.severity})")

        lines.extend(["", "建议：", "- 尽量避开周末上午高峰", "- 出发前再次确认官方公告与预约要求"])
        if state.limitations:
            lines.extend(["", "限制说明：", *[f"- {l}" for l in state.limitations[:4]]])
        return "\n".join(lines)

    @staticmethod
    def _evidence_summary_lines(state: TravelAgentState, fact_sheet: PlaceFactSheet | None = None) -> list[str]:
        if state.field_evidence_summary:
            return [
                f"- {row['field']}: {row['value']} ({', '.join(row.get('source_names') or []) or 'aggregated'})"
                for row in state.field_evidence_summary[:8]
            ]
        if fact_sheet:
            return [
                f"- {row['field']}: {row['value']}"
                for row in fact_sheet.to_field_evidence_summary()[:5]
            ]
        return [f"- {e.source_name} ({e.source_type.value})" for e in state.evidence[:5] if isinstance(e, Evidence)]

    @staticmethod
    def compose_compare(
        ranked: list[tuple[str, RecommendationResult, ReviewAspectResult, PlaceFactSheet]],
        state: TravelAgentState,
    ) -> str:
        lines: list[str] = []
        if state.place_contexts:
            countries = {c.country for c in state.place_contexts if c.country}
            cities = {c.city for c in state.place_contexts if c.city}
            if len(countries) > 1:
                lines.append("注意：以下为跨国比较，交通成本和行程组合复杂度更高。")
            elif len(cities) > 1:
                lines.append("注意：以下为跨城比较，交通成本和行程组合复杂度更高。")
            if lines:
                lines.append("")

        lines += ["总体推荐：", *[f"{i + 1}. {name}（{rec.overall_recommendation}, score={rec.overall_score}）" for i, (name, rec, _, _) in enumerate(ranked)]]
        lines += ["", "比较表：", "景点 | 适合度 | 交通 | 步行强度 | 拥挤风险 | 亮点 | 风险 | 推荐人群"]
        for row in state.structured_result.get("comparison", []):
            lines.append(
                f"{row['place_name']} | {row['suitability']} | {row['transport']} | {row['walking_intensity']} | {row['crowd_risk']} | {row['highlights']} | {row['risks']} | {row['recommended_for']}"
            )
        lines += ["", "最终推荐："]
        if ranked:
            best = ranked[0][0]
            lines.append(f"如果只能选一个，优先推荐 {best}。")
            if len(ranked) > 1:
                lines.append(f"时间充足可将 {ranked[0][0]} 与 {ranked[1][0]} 分区组合，避免连续高坡道。")
        return "\n".join(lines)

    @staticmethod
    def compose_itinerary(plan: ItineraryPlan, state: TravelAgentState) -> str:
        lines = [
            "行程结论：",
            plan.title,
            "",
            "时间安排：",
            *[f"{item.start_time} - {item.end_time} {item.activity}" + (f"（{item.place_name}）" if item.place_name else "") for item in plan.items],
            "",
            "交通：",
            *[f"- {t}" for t in plan.transport_summary],
            "",
            "餐饮：",
            *[f"- {f}" for f in plan.food_suggestions],
            "",
            "备选方案：",
            *[f"- {b}" for b in plan.backup_plans],
            "",
            "注意事项：",
            *[f"- {c}" for c in plan.cautions],
            "",
            "最终建议：",
            "- 以上为轻量一日文化游框架，具体开放时间与预约政策请出发前确认。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _conclusion_text(rec: RecommendationResult, place_name: str) -> str:
        mapping = {
            "highly_recommended": f"{place_name} 值得前往，整体匹配度较高。",
            "recommended": f"{place_name} 推荐前往，但建议避开高峰并控制强度。",
            "conditional": f"{place_name} 可以前往，但需要满足特定条件并做取舍。",
            "not_recommended": f"{place_name} 当前条件下不太推荐。",
            "insufficient_info": f"{place_name} 信息不足，建议出发前再确认。",
        }
        return mapping.get(rec.overall_recommendation, mapping["conditional"])

    @staticmethod
    def build_comparison_rows(
        ranked: list[tuple[str, RecommendationResult, ReviewAspectResult, PlaceFactSheet]],
    ) -> list[ComparisonRow]:
        rows = []
        for name, rec, review, sheet in ranked:
            rows.append(
                ComparisonRow(
                    place_name=name,
                    suitability=rec.overall_recommendation,
                    transport="便利" if ComposerAgent._level_high(sheet.transport_convenience, 0.75) else "一般",
                    walking_intensity="高" if ComposerAgent._level_high(sheet.walking_intensity) else "中低",
                    crowd_risk="高" if ComposerAgent._level_high(sheet.crowd_risk, 0.7) else "中",
                    highlights="文化地标" if (sheet.first_timer_fit or 0) > 0.8 else "特色体验",
                    risks="; ".join(rec.risks[:2]),
                    recommended_for=", ".join(rec.best_for[:2]) or "一般游客",
                )
            )
        return rows


class ItineraryAgent:
    @classmethod
    def _registered_only(cls, places: list[str]) -> list[str]:
        catalog = get_place_catalog()
        result: list[str] = []
        for place in places:
            canonical = catalog.normalize_place_name(place) or place
            if canonical not in result and catalog.is_registered(canonical):
                result.append(canonical)
        return result

    @classmethod
    def build(cls, goal: UserGoal) -> ItineraryPlan:
        catalog = get_place_catalog()
        country = goal.destination_country or "South Korea"
        city = goal.destination_city or "Seoul"
        if goal.start_location:
            resolved = resolve_start_location(goal.start_location)
            if resolved:
                country, city, _ = resolved

        raw_places = CULTURAL_SETS.get((country, city), [])
        places = cls._registered_only(raw_places)
        if goal.place_candidates:
            places = cls._registered_only(goal.place_candidates[:4]) or places
        if not places:
            places = catalog.registered_places_for_city(country, city)[:3]
        if not places:
            places = catalog.registered_places_for_country(country)[:3]

        pace = goal.pace.value if goal.pace.value != "unknown" else "relaxed"
        slots = [("09:00", "11:30"), ("12:30", "14:00"), ("14:30", "17:00"), ("17:30", "19:00")]
        items: list[ItineraryItem] = []
        for idx, place in enumerate(places[:3]):
            start, end = slots[idx]
            items.append(
                ItineraryItem(
                    start_time=start,
                    end_time=end,
                    activity="Visit",
                    place_name=place,
                    transport_note=f"Public transit between stops in {city}",
                    notes=["Go early to reduce queues"],
                )
            )
        if len(places) > 1:
            items.insert(
                1,
                ItineraryItem(
                    start_time="11:45",
                    end_time="12:15",
                    activity="Lunch break",
                    place_name=None,
                    transport_note="Walk to nearby dining area",
                ),
            )
        return ItineraryPlan(
            title=f"{city} {'relaxed' if pace == 'relaxed' else 'balanced'} one-day route",
            pace=pace,
            items=items,
            transport_summary=[f"Use metro/bus within {city}; allow buffer time between attractions."],
            food_suggestions=[f"Dine near {places[0]} or central {city} districts; specific restaurants not verified."],
            backup_plans=[
                "Rainy day: prioritize indoor palace/museum segments.",
                "Crowded day: start 1 hour earlier.",
                "Low energy: drop the last viewpoint stop.",
            ],
            cautions=["Verify reservation requirements.", "Carry ID if required.", "Check official closing days."],
        )
