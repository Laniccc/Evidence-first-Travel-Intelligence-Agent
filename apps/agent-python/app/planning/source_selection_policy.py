"""Planning policy for selecting source families and resolving claim conflicts."""

from app.evidence.evidence_model import ClaimType, Evidence
from app.evidence.source_priority_policy import SourcePriorityPolicy
from app.understanding.user_query import IntentType, UserGoal


class SourceSelectionPolicy:
    """Decide which tools to invoke per intent and query plan."""

    INTENT_TOOLS: dict[str, list[str]] = {
        IntentType.SINGLE_PLACE.value: ["official", "places", "transit", "reviews", "restaurant", "weather"],
        IntentType.COMPARE_PLACES.value: ["official", "places", "transit", "reviews"],
        IntentType.ITINERARY.value: ["official", "transit", "restaurant", "weather", "lodging"],
        IntentType.WEATHER_RISK.value: ["official", "weather", "reviews", "transit"],
        IntentType.TRANSPORT.value: ["transit", "places", "official"],
        IntentType.FOOD_LODGING.value: ["restaurant", "lodging", "places"],
        IntentType.GENERAL.value: ["official", "places", "reviews"],
    }

    @classmethod
    def select_tools(cls, goal: UserGoal, *, include_weather: bool = True) -> list[str]:
        tools = list(cls.INTENT_TOOLS.get(goal.intent_type.value, cls.INTENT_TOOLS[IntentType.GENERAL.value]))
        if not include_weather and "weather" in tools:
            tools.remove("weather")
        if goal.travel_date and "weather" not in tools and goal.intent_type in {
            IntentType.SINGLE_PLACE,
            IntentType.WEATHER_RISK,
            IntentType.ITINERARY,
        }:
            tools.append("weather")
        if goal.party and goal.intent_type == IntentType.SINGLE_PLACE:
            for extra in ("transit", "reviews"):
                if extra not in tools:
                    tools.append(extra)
        return tools

    @staticmethod
    def resolve_conflict_winners(evidence: list[Evidence], field: str) -> str | None:
        claim_type = {
            "opening_hours": ClaimType.OPENING_HOURS,
            "ticket_price": ClaimType.TICKET_PRICE,
        }.get(field)
        if not claim_type:
            return None
        best_source = None
        best_rank = 999
        for evidence_item in evidence:
            if not isinstance(evidence_item, Evidence):
                continue
            for claim in evidence_item.claims:
                if claim.claim_type == claim_type:
                    rank = SourcePriorityPolicy.rank(evidence_item.source_type)
                    if rank < best_rank:
                        best_rank = rank
                        best_source = evidence_item.source_name
        return best_source
