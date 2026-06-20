from app.schemas.itinerary import ItineraryItem, ItineraryPlan
from app.schemas.response import ComparisonRow, RecommendationResult
from app.schemas.review import ReviewAspectResult
from app.schemas.user_query import IntentType, TravelAgentState, UserGoal
from app.tools.mock_data import LOCATION_ALIASES, PLACE_REGISTRY


class ComposerAgent:
    @staticmethod
    def _is_zh(text: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in text)

    @staticmethod
    def compose_single(place_name: str, recommendation: RecommendationResult, review: ReviewAspectResult, state: TravelAgentState) -> str:
        zh = ComposerAgent._is_zh(state.raw_user_query)
        meta = PLACE_REGISTRY.get(place_name, {})
        lines = [
            "结论：",
            ComposerAgent._conclusion_text(recommendation, place_name, zh),
            "",
            "适合你吗：" if zh else "适合你吗：",
            *([f"- {p.persona}: {p.fit} — {p.reason}" for p in review.persona_implications] or ["- 请结合同行人体力与偏好判断。"]),
            "",
            "核心依据：",
            *[f"{i + 1}. {r}" for i, r in enumerate(recommendation.main_reasons[:4])],
        ]
        if zh:
            lines.extend(
                [
                    f"- 文化价值：{'高' if meta.get('first_timer_fit', 0) > 0.8 else '中等'}",
                    f"- 交通：{'较便利' if meta.get('transport_convenience', 0) > 0.75 else '一般'}",
                    f"- 开放时间：请以官方信息为准（证据已检索）",
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
                    f"- 步行强度：{'偏高' if meta.get('walking_intensity', 0) > 0.65 else '中等'}",
                    f"- 拥挤风险：{'较高' if meta.get('crowd_risk', 0) > 0.7 else '中等'}",
                    f"- 人流：{'高峰时段明显' if meta.get('crowd_risk', 0) > 0.7 else '可控'}",
                    f"- 预约：{meta.get('reservation', '请出发前确认')}",
                ]
            )
        lines.extend([*[f"- {l}" for l in state.limitations[:3]], "", "证据摘要：", *[f"- {e.source_name} ({e.source_type.value})" for e in state.evidence[:5]]])
        return "\n".join(lines)

    @staticmethod
    def compose_compare(ranked: list[tuple[str, RecommendationResult, ReviewAspectResult]], state: TravelAgentState) -> str:
        lines = ["总体推荐：", *[f"{i + 1}. {name}（{rec.overall_recommendation}, score={rec.overall_score}）" for i, (name, rec, _) in enumerate(ranked)]]
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
    def _conclusion_text(rec: RecommendationResult, place_name: str, zh: bool = True) -> str:
        mapping = {
            "highly_recommended": f"{place_name} 值得前往，整体匹配度较高。",
            "recommended": f"{place_name} 推荐前往，但建议避开高峰并控制强度。",
            "conditional": f"{place_name} 可以前往，但需要满足特定条件并做取舍。",
            "not_recommended": f"{place_name} 当前条件下不太推荐。",
            "insufficient_info": f"{place_name} 信息不足，建议出发前再确认。",
        }
        return mapping.get(rec.overall_recommendation, mapping["conditional"])

    @staticmethod
    def build_comparison_rows(ranked: list[tuple[str, RecommendationResult, ReviewAspectResult]]) -> list[ComparisonRow]:
        rows = []
        for name, rec, review in ranked:
            meta = PLACE_REGISTRY.get(name, {})
            rows.append(
                ComparisonRow(
                    place_name=name,
                    suitability=rec.overall_recommendation,
                    transport="便利" if meta.get("transport_convenience", 0) > 0.75 else "一般",
                    walking_intensity="高" if meta.get("walking_intensity", 0) > 0.65 else "中低",
                    crowd_risk="高" if meta.get("crowd_risk", 0) > 0.7 else "中",
                    highlights="文化地标" if meta.get("first_timer_fit", 0) > 0.8 else "特色体验",
                    risks="; ".join(rec.risks[:2]),
                    recommended_for=", ".join(rec.best_for[:2]) or "一般游客",
                )
            )
        return rows


class ItineraryAgent:
    CULTURAL_SETS = {
        ("South Korea", "Seoul"): ["Gyeongbokgung Palace", "Bukchon Hanok Village", "N Seoul Tower"],
        ("Japan", "Kyoto"): ["Kiyomizu-dera", "Arashiyama Bamboo Grove"],
        ("Japan", "Tokyo"): ["Senso-ji", "Meiji Shrine"],
        ("China", "Beijing"): ["Forbidden City", "Temple of Heaven"],
    }

    @classmethod
    def build(cls, goal: UserGoal) -> ItineraryPlan:
        country = goal.destination_country or "South Korea"
        city = goal.destination_city or "Seoul"
        if goal.start_location:
            for alias, (c_country, c_city, _) in LOCATION_ALIASES.items():
                if goal.start_location.lower() in {alias.lower(), alias}:
                    country, city = c_country, c_city
        places = cls.CULTURAL_SETS.get((country, city)) or list(PLACE_REGISTRY.keys())[:3]
        if goal.place_candidates:
            places = goal.place_candidates[:4] or places
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
                    notes=["Go early to reduce queues"] if PLACE_REGISTRY.get(place, {}).get("crowd_risk", 0) > 0.7 else [],
                )
            )
        if len(places) > 1:
            items.insert(1, ItineraryItem(start_time="11:45", end_time="12:15", activity="Lunch break", place_name=None, transport_note="Walk to nearby dining area"))
        return ItineraryPlan(
            title=f"{city} {'relaxed' if pace == 'relaxed' else 'balanced'} one-day route",
            pace=pace,
            items=items,
            transport_summary=[f"Use metro/bus within {city}; allow buffer time between attractions."],
            food_suggestions=[f"Dine near {places[0]} or central {city} districts; specific restaurants not verified."],
            backup_plans=["Rainy day: prioritize indoor palace/museum segments.", "Crowded day: start 1 hour earlier.", "Low energy: drop the last viewpoint stop."],
            cautions=["Verify reservation requirements.", "Carry ID if required.", "Check official closing days."],
        )
