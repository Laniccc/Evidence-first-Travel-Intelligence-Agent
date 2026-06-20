from app.schemas.response import RecommendationResult
from app.schemas.review import ReviewAspectName, ReviewAspectResult
from app.schemas.user_query import IntentType, PartyType, UserGoal
from app.tools.mock_data import PLACE_REGISTRY


class TravelSuitabilityScorer:
    @staticmethod
    def score_place(place_name: str, review_result: ReviewAspectResult, goal: UserGoal) -> RecommendationResult:
        meta = PLACE_REGISTRY.get(place_name, {})
        weights = TravelSuitabilityScorer._weights(goal)

        def aspect_score(name: ReviewAspectName, fallback_key: str) -> float:
            found = next((a for a in review_result.aspects if a.aspect == name), None)
            if found:
                if found.sentiment == "positive":
                    return 0.8
                if found.sentiment == "mixed":
                    return 0.55
                if found.sentiment == "negative":
                    return 0.35
            val = meta.get(fallback_key)
            if val is not None:
                return 1.0 - val if fallback_key in {"walking_intensity", "crowd_risk"} else val
            return 0.5

        dims = {
            "interest_match": aspect_score(ReviewAspectName.FIRST_TIMER_FIT, "first_timer_fit"),
            "transport": aspect_score(ReviewAspectName.TRANSPORT_CONVENIENCE, "transport_convenience"),
            "walking": aspect_score(ReviewAspectName.WALKING_INTENSITY, "walking_intensity"),
            "weather": 0.82,
            "crowd": aspect_score(ReviewAspectName.CROWD_LEVEL, "crowd_risk"),
            "reservation": 0.55 if "reservation required" in meta.get("reservation", "").lower() else 0.75,
            "food": 0.7,
            "review_consistency": 0.72,
            "confidence": 0.78,
        }

        overall = sum(dims[k] * weights.get(k, 1.0) for k in dims) / sum(weights.values())
        recommendation = TravelSuitabilityScorer._label(overall, goal, meta, review_result)
        best_for, not_ideal = TravelSuitabilityScorer._audiences(goal, meta, review_result)
        risks = TravelSuitabilityScorer._risks(meta, review_result)
        return RecommendationResult(
            overall_recommendation=recommendation,
            overall_score=round(overall, 3),
            confidence=0.78,
            best_for=best_for,
            not_ideal_for=not_ideal,
            recommended_time="Morning, weekday if possible" if meta.get("crowd_risk", 0) > 0.65 else "Flexible hours",
            main_reasons=TravelSuitabilityScorer._reasons(meta, review_result, goal),
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
    def _label(score: float, goal: UserGoal, meta: dict, review: ReviewAspectResult) -> str:
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
    def _audiences(goal: UserGoal, meta: dict, review: ReviewAspectResult) -> tuple[list[str], list[str]]:
        best, bad = [], []
        if meta.get("first_timer_fit", 0) > 0.8:
            best.append("First-time visitors")
        if meta.get("elderly_friendliness", 0) > 0.55:
            best.append("Travelers with moderate mobility")
        else:
            bad.append("Travelers needing low walking intensity")
        if PartyType.COUPLE in goal.party and meta.get("photo_experience", 0) > 0.8:
            best.append("Couples seeking scenic spots")
        if meta.get("crowd_risk", 0) > 0.75:
            bad.append("Visitors avoiding peak crowds")
        return best, bad

    @staticmethod
    def _risks(meta: dict, review: ReviewAspectResult) -> list[str]:
        risks = []
        if meta.get("crowd_risk", 0) > 0.7:
            risks.append("High crowd risk on weekends and holidays.")
        if meta.get("walking_intensity", 0) > 0.65:
            risks.append("Significant walking or slopes.")
        if "reservation" in meta and "required" in meta["reservation"].lower():
            risks.append("Advance reservation may be required.")
        risks.append("Confirm opening hours on official site before visiting.")
        return risks

    @staticmethod
    def _reasons(meta: dict, review: ReviewAspectResult, goal: UserGoal) -> list[str]:
        reasons = [review.review_summary]
        if meta.get("first_timer_fit", 0) > 0.8:
            reasons.append("Strong landmark value for first-time visitors.")
        if meta.get("transport_convenience", 0) > 0.75:
            reasons.append("Public transit access is relatively convenient.")
        if PartyType.ELDERLY in goal.party and meta.get("walking_intensity", 0) > 0.6:
            reasons.append("Walking intensity may be demanding for elderly companions.")
        return reasons

    @staticmethod
    def compare(recommendations: list[tuple[str, RecommendationResult]], goal: UserGoal) -> list[tuple[str, RecommendationResult]]:
        return sorted(recommendations, key=lambda x: x[1].overall_score, reverse=True)
