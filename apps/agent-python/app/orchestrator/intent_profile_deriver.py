"""Rule-based IntentProfile derivation from SemanticFrame (+ optional LLM patch)."""

from __future__ import annotations

import re

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

_COMPARE_PATTERN = re.compile(r"哪个更|还是|vs|对比|比较|只能选一个|选一个去", re.I)


class IntentProfileDeriver:
    def derive(self, frame: SemanticFrame | None) -> IntentProfile | None:
        if frame is None:
            return None
        needs = set(frame.information_needs or [])
        places = list(frame.entities.places or [])
        subtypes = list(dict.fromkeys(frame.information_needs or []))

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

        if frame.requires_exact_fact or needs & _HARD_FACT_NEEDS:
            flags["official"] = True
            return (
                PrimaryIntent.LOOKUP,
                EvidenceSensitivity.HARD_FACT,
                AnswerStyle.DIRECT_FACT,
                flags,
            )

        if frame.decision_type == DecisionType.NEARBY_SEARCH or needs & {"nearby_food", "nearby_poi", "nearby_hotel"}:
            flags["review"] = True
            return (
                PrimaryIntent.NEARBY,
                EvidenceSensitivity.EVIDENCE_PREFERRED,
                AnswerStyle.RECOMMENDATION_LIST,
                flags,
            )

        if (
            frame.requires_live_data
            or frame.time_scope in {TimeScope.CURRENT, TimeScope.SPECIFIC_DATE}
            or needs & _LIVE_NEEDS
        ):
            flags["live"] = True
            return (
                PrimaryIntent.REALTIME_CHECK,
                EvidenceSensitivity.LIVE_REQUIRED,
                AnswerStyle.DIRECT_FACT,
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

        if (
            frame.decision_type == DecisionType.ROUTE_PLAN
            or frame.task_family == TaskFamily.PLANNING
            or needs & {"route_plan", "itinerary_feasibility", "transport_planning", "duration"}
        ):
            flags["route"] = True
            return (
                PrimaryIntent.PLANNING,
                EvidenceSensitivity.EVIDENCE_PREFERRED,
                AnswerStyle.ITINERARY,
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
