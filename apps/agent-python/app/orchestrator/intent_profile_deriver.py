"""Rule-based IntentProfile derivation from SemanticFrame (+ optional LLM patch)."""

from __future__ import annotations

import re

from app.orchestrator.information_need_aliases import (
    infer_nearby_need_from_text,
    is_nearby_need,
    nearby_needs_set,
    normalize_information_needs,
)
from app.schemas.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    IntentProfile,
    PrimaryIntent,
)
from app.schemas.semantic_frame import DecisionType, SemanticFrame, TaskFamily, TimeScope

_HARD_FACT_NEEDS = frozenset(
    {
        "ticket_price",
        "opening_hours",
        "temporary_closure",
        "reservation_policy",
        "reservation_required",
        "seasonal_operation_status",
        "road_opening_period",
        "elevation",
        "altitude",
        "height_elevation",
    }
)

_REVIEW_CHECK_NEEDS = frozenset(
    {
        "commercialization_risk",
        "crowd_level",
        "crowd_risk",
        "queue_time",
        "current_crowd",
        "current_crowd_estimate",
        "value_for_money",
        "review_summary",
    }
)

_LIVE_NEEDS = frozenset(
    {
        "today_weather",
        "weather_today",
        "current_weather",
        "forecast",
        "weather",
        "traffic_status",
        "congestion_risk",
        "current_crowd",
        "current_crowd_estimate",
        "queue_time",
        "daily_notice",
    }
)

_NEARBY_NEEDS = frozenset(
    {
        "nearby_food",
    "nearby_dining",
    "nearby_restaurant",
    "restaurant_recommendation",
    "food_recommendation",
    "food_nearby",
    "nearby_places",
        "nearby_poi",
        "nearby_hotel",
        "nearby_lodging",
        "nearby_rest_area",
        "nearby_parking",
        "nearby_toilet",
        "nearby_station",
        "nearby_amenity",
        "nearby_accommodation",
        "nearby_attraction",
    }
)

_COMPARE_PATTERN = re.compile(r"哪个更|还是|vs|对比|比较|只能选一个|选一个去", re.I)
_NEARBY_PATTERN = re.compile(
    r"附近|周边|顺路|附近吃|好吃的|停车|厕所|宾馆|酒店|住宿|休息区|周边吃|周边玩",
    re.I,
)
_LIVE_TEXT_PATTERN = re.compile(
    r"今天|明天|现在|这两天|周末|会下雨|能走吗|路况|开放吗",
    re.I,
)
_TICKET_TEXT_PATTERN = re.compile(r"门票|票价|多少钱|多少元|价格|成人票|购票|预约", re.I)
_ELEVATION_TEXT_PATTERN = re.compile(r"海拔|主峰|最高峰|山体高度|高度多少|elevation|altitude", re.I)
_ROUTE_TEXT_PATTERN = re.compile(
    r"从.+到.+(怎么走|坐地铁|坐公交|打车|开车|多久|多长时间|路线)|"
    r"地铁|公交|打车|出租车|网约车|怎么去|怎么走|路线|换乘|车程|耗时|多远",
    re.I,
)
_LIVE_TRAFFIC_TEXT_PATTERN = re.compile(r"现在.+堵|路上堵|实时路况|当前路况|堵吗|拥堵", re.I)
_REVIEW_TEXT_PATTERN = re.compile(
    r"口碑|评价|评论|好评|差评|避雷|坑不坑|排队久不久|排队久|"
    r"人多不多|商业化|体验怎么样",
    re.I,
)


class IntentProfileDeriver:
    def derive(self, frame: SemanticFrame | None) -> IntentProfile | None:
        if frame is None:
            return None
        raw_needs = list(frame.information_needs or [])
        text = f"{frame.raw_query} {frame.normalized_request}".strip()
        needs = set(normalize_information_needs(raw_needs, text=text))
        needs |= nearby_needs_set(raw_needs)
        places = list(frame.entities.places or [])
        subtypes = list(dict.fromkeys(raw_needs))

        primary, sensitivity, style, flags = self._rules(frame, needs, places)
        sensitivity = self._apply_sensitivity_overrides(sensitivity, needs, frame, primary)

        return IntentProfile(
            primary_intent=primary,
            intent_subtypes=subtypes,
            evidence_sensitivity=sensitivity,
            answer_style=style,
            requires_geo_resolution=flags.get("geo", True),
            requires_official_source=flags.get("official", False),
            requires_review_signal=flags.get("review", False),
            requires_route_planning=flags.get("route", False),
            requires_live_data=flags.get("live", False),
            confidence=float(frame.confidence or 0.7),
            derivation="rules",
        )

    def _rules(
        self,
        frame: SemanticFrame,
        needs: set[str],
        places: list[str],
    ) -> tuple[PrimaryIntent, EvidenceSensitivity, AnswerStyle, dict[str, bool]]:
        flags: dict[str, bool] = {"geo": True, "official": False, "review": False, "route": False, "live": False}
        text = f"{frame.raw_query} {frame.normalized_request}"

        if frame.needs_clarification or "place_reference" in frame.missing_slots:
            if not places and not frame.entities.city:
                return (
                    PrimaryIntent.CLARIFICATION,
                    EvidenceSensitivity.EVIDENCE_PREFERRED,
                    AnswerStyle.CLARIFICATION,
                    flags,
                )

        if (
            frame.decision_type == DecisionType.ROUTE_PLAN
            or frame.task_family in {TaskFamily.PLANNING, TaskFamily.TRANSPORT}
            or needs & {"route_plan", "itinerary_feasibility", "transport_planning", "duration", "distance"}
            or (_ROUTE_TEXT_PATTERN.search(text) and not _LIVE_TRAFFIC_TEXT_PATTERN.search(text))
        ):
            flags["route"] = True
            return (
                PrimaryIntent.PLANNING,
                EvidenceSensitivity.EVIDENCE_PREFERRED,
                AnswerStyle.ITINERARY,
                flags,
            )

        # Nearby POI recommendation beats hard_fact / advisory when user asks 附近+宾馆/美食/…
        if (
            frame.decision_type == DecisionType.NEARBY_SEARCH
            or needs & _NEARBY_NEEDS
            or nearby_needs_set(list(needs))
            or _NEARBY_PATTERN.search(text)
        ):
            flags["review"] = True
            return (
                PrimaryIntent.NEARBY,
                EvidenceSensitivity.EVIDENCE_PREFERRED,
                AnswerStyle.RECOMMENDATION_LIST,
                flags,
            )

        if frame.task_family == TaskFamily.COMPARISON or len(places) >= 2 or _COMPARE_PATTERN.search(text):
            flags["review"] = True
            return (
                PrimaryIntent.COMPARISON,
                EvidenceSensitivity.EVIDENCE_PREFERRED,
                AnswerStyle.COMPARISON,
                flags,
            )

        explicit_live_text = bool(_LIVE_TEXT_PATTERN.search(text) or _LIVE_TRAFFIC_TEXT_PATTERN.search(text))
        if _REVIEW_TEXT_PATTERN.search(text) and not explicit_live_text:
            flags["review"] = True
            return (
                PrimaryIntent.REVIEW_CHECK,
                EvidenceSensitivity.EXPERIENCE_BASED,
                AnswerStyle.ADVISORY,
                flags,
            )

        if _TICKET_TEXT_PATTERN.search(text) or _ELEVATION_TEXT_PATTERN.search(text):
            flags["official"] = True
            return (
                PrimaryIntent.LOOKUP,
                EvidenceSensitivity.HARD_FACT,
                AnswerStyle.DIRECT_FACT,
                flags,
            )

        # Hard fact lookup (ticket, hours, closure) — not generic nearby POI lists
        if frame.requires_exact_fact or needs & _HARD_FACT_NEEDS:
            flags["official"] = True
            return (
                PrimaryIntent.LOOKUP,
                EvidenceSensitivity.HARD_FACT,
                AnswerStyle.DIRECT_FACT,
                flags,
            )

        # Override 2: live_fact beats review/advisory
        live_by_text = (
            frame.time_scope in {TimeScope.CURRENT, TimeScope.SPECIFIC_DATE}
            and _LIVE_TEXT_PATTERN.search(text)
        )
        if frame.requires_live_data or needs & _LIVE_NEEDS or live_by_text:
            flags["live"] = True
            return (
                PrimaryIntent.REALTIME_CHECK,
                EvidenceSensitivity.LIVE_REQUIRED,
                AnswerStyle.DIRECT_FACT,
                flags,
            )

        if (
            needs & _REVIEW_CHECK_NEEDS
            and frame.decision_type != DecisionType.WHETHER_TO_GO
            and frame.task_family != TaskFamily.SUITABILITY
        ):
            flags["review"] = True
            return (
                PrimaryIntent.REVIEW_CHECK,
                EvidenceSensitivity.EXPERIENCE_BASED,
                AnswerStyle.ADVISORY,
                flags,
            )

        if (
            frame.task_family in {TaskFamily.SUITABILITY, TaskFamily.ADVISORY}
            or frame.decision_type
            in {DecisionType.WHETHER_TO_GO, DecisionType.GENERAL_ADVICE, DecisionType.HOW_TO_CHOOSE}
        ):
            flags["review"] = True
            return (
                PrimaryIntent.ADVISORY,
                EvidenceSensitivity.EXPERIENCE_BASED,
                AnswerStyle.ADVISORY,
                flags,
            )

        if frame.decision_type == DecisionType.FACT_LOOKUP or frame.task_family == TaskFamily.FACT_LOOKUP:
            flags["official"] = True
            return (
                PrimaryIntent.LOOKUP,
                EvidenceSensitivity.EVIDENCE_PREFERRED,
                AnswerStyle.DIRECT_FACT,
                flags,
            )

        flags["review"] = True
        return (
            PrimaryIntent.ADVISORY,
            EvidenceSensitivity.EVIDENCE_PREFERRED,
            AnswerStyle.ADVISORY,
            flags,
        )

    @staticmethod
    def _apply_sensitivity_overrides(
        sensitivity: EvidenceSensitivity,
        needs: set[str],
        frame: SemanticFrame,
        primary: PrimaryIntent,
    ) -> EvidenceSensitivity:
        if needs & _HARD_FACT_NEEDS or frame.requires_exact_fact:
            return EvidenceSensitivity.HARD_FACT
        if primary == PrimaryIntent.REVIEW_CHECK:
            return sensitivity
        if frame.requires_live_data or needs & _LIVE_NEEDS:
            return EvidenceSensitivity.LIVE_REQUIRED
        if (
            frame.can_answer_with_model_prior
            and primary == PrimaryIntent.ADVISORY
            and sensitivity == EvidenceSensitivity.EXPERIENCE_BASED
            and frame.decision_type in {DecisionType.BEST_TIME_TO_VISIT, DecisionType.GENERAL_ADVICE}
        ):
            return EvidenceSensitivity.MODEL_PRIOR_ALLOWED
        return sensitivity
