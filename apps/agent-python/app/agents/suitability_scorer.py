from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.response import RecommendationResult
from app.schemas.review import ReviewAspectName, ReviewAspectResult
from app.schemas.user_query import ConflictRecord, PartyType, UserGoal


class TravelSuitabilityScorer:
    @staticmethod
    def score_place(
        place_name: str,
        fact_sheet: PlaceFactSheet,
        review_result: ReviewAspectResult,
        goal: UserGoal,
        conflicts: list[ConflictRecord] | None = None,
    ) -> RecommendationResult:
        weights = TravelSuitabilityScorer._weights(goal)
        conflict_penalty = 0.05 * len(conflicts or [])

        def aspect_score(name: ReviewAspectName, fact_field: str | None = None, invert: bool = False) -> float:
            found = next((a for a in review_result.aspects if a.aspect == name), None)
            if found:
                if found.sentiment == "positive":
                    base = 0.8
                elif found.sentiment == "mixed":
                    base = 0.55
                else:
                    base = 0.35
                return 1.0 - base if invert else base
            if fact_field and fact_sheet.has_field(fact_field):
                val = getattr(fact_sheet, fact_field)
                if isinstance(val, (int, float)):
                    return 1.0 - val if invert else val
            return 0.5

        reservation_text = (fact_sheet.reservation_policy or "").lower()
        dims = {
            "interest_match": aspect_score(ReviewAspectName.FIRST_TIMER_FIT, "first_timer_fit"),
            "transport": aspect_score(ReviewAspectName.TRANSPORT_CONVENIENCE, "transport_convenience"),
            "walking": aspect_score(ReviewAspectName.WALKING_INTENSITY, "walking_intensity", invert=True),
            "weather": 0.82 if fact_sheet.weather else 0.5,
            "crowd": aspect_score(ReviewAspectName.CROWD_LEVEL, "crowd_risk", invert=True),
            "reservation": 0.55 if "required" in reservation_text else 0.75,
            "food": 0.7 if fact_sheet.food_nearby else 0.5,
            "review_consistency": 0.72 if review_result.aspects else 0.45,
            "confidence": fact_sheet.confidence or 0.5,
        }

        overall = sum(dims[k] * weights.get(k, 1.0) for k in dims) / sum(weights.values())
        recommendation = TravelSuitabilityScorer._label(overall)
        best_for, not_ideal = TravelSuitabilityScorer._audiences(fact_sheet, review_result, goal)
        risks = TravelSuitabilityScorer._risks(fact_sheet, review_result)
        crowd = fact_sheet.crowd_risk or 0.5
        return RecommendationResult(
            overall_recommendation=recommendation,
            overall_score=round(overall, 3),
            confidence=max(0.2, round((fact_sheet.confidence or 0.5) - conflict_penalty, 3)),
            best_for=best_for,
            not_ideal_for=not_ideal,
            recommended_time="Morning, weekday if possible" if crowd > 0.65 else "Flexible hours",
            main_reasons=TravelSuitabilityScorer._reasons(fact_sheet, review_result, goal),
            risks=risks,
            alternatives=[],
        )

    @staticmethod
    def _weights(goal: UserGoal) -> dict[str, float]:
        w = {k: 1.0 for k in ["interest_match", "transport", "walking", "weather", "crowd", "reservation", "food", "review_consistency", "confidence"]}
        if PartyType.ELDERLY in goal.party:
            w["walking"] = 2.0
            w["crowd"] = 1.6
            w["transport"] = 1.5
        if PartyType.FAMILY in goal.party or PartyType.CHILDREN in goal.party:
            w["crowd"] = 1.5
            w["food"] = 1.4
        if PartyType.COUPLE in goal.party:
            w["interest_match"] = 1.3
        if goal.pace.value == "relaxed":
            w["walking"] = 1.5
            w["crowd"] = 1.4
        return w

    @staticmethod
    def _label(score: float) -> str:
        if score >= 0.75:
            return "highly_recommended"
        if score >= 0.6:
            return "recommended"
        if score >= 0.45:
            return "conditional"
        if score < 0.35:
            return "not_recommended"
        return "conditional"

    @staticmethod
    def _audiences(fact_sheet: PlaceFactSheet, review: ReviewAspectResult, goal: UserGoal) -> tuple[list[str], list[str]]:
        best, bad = [], []
        if (fact_sheet.first_timer_fit or 0) > 0.8:
            best.append("First-time visitors")
        if (fact_sheet.accessibility or 0) > 0.55 or any(
            a.aspect == ReviewAspectName.ELDERLY_FRIENDLINESS and a.sentiment != "negative" for a in review.aspects
        ):
            best.append("Travelers with moderate mobility")
        else:
            bad.append("Travelers needing low walking intensity")
        if PartyType.COUPLE in goal.party and any(a.aspect == ReviewAspectName.PHOTO_EXPERIENCE for a in review.aspects):
            best.append("Couples seeking scenic spots")
        if (fact_sheet.crowd_risk or 0) > 0.75:
            bad.append("Visitors avoiding peak crowds")
        return best, bad

    @staticmethod
    def _risks(fact_sheet: PlaceFactSheet, review: ReviewAspectResult) -> list[str]:
        risks = []
        if (fact_sheet.crowd_risk or 0) > 0.7:
            risks.append("High crowd risk on weekends and holidays.")
        if (fact_sheet.walking_intensity or 0) > 0.65:
            risks.append("Significant walking or slopes.")
        if fact_sheet.reservation_policy and "required" in fact_sheet.reservation_policy.lower():
            risks.append("Advance reservation may be required.")
        if fact_sheet.official_hours:
            risks.append(f"Confirm opening hours ({fact_sheet.official_hours}) on official site before visiting.")
        else:
            risks.append("Confirm opening hours on official site before visiting.")
        return risks

    @staticmethod
    def _reasons(fact_sheet: PlaceFactSheet, review: ReviewAspectResult, goal: UserGoal) -> list[str]:
        reasons = [review.review_summary]
        if (fact_sheet.first_timer_fit or 0) > 0.8:
            reasons.append("Strong landmark value for first-time visitors.")
        if (fact_sheet.transport_convenience or 0) > 0.75:
            reasons.append("Public transit access is relatively convenient.")
        if fact_sheet.transit_summary:
            reasons.append(f"Transit evidence: {fact_sheet.transit_summary}")
        if PartyType.ELDERLY in goal.party and (fact_sheet.walking_intensity or 0) > 0.6:
            reasons.append("Walking intensity may be demanding for elderly companions.")
        return reasons

    @staticmethod
    def compare(recommendations: list[tuple[str, RecommendationResult]], goal: UserGoal) -> list[tuple[str, RecommendationResult]]:
        return sorted(recommendations, key=lambda x: x[1].overall_score, reverse=True)
