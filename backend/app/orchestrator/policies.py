from app.schemas.evidence import SourceType
from app.schemas.user_query import IntentType, UserGoal

SOURCE_PRIORITY = {
    "user_provided": 0,
    SourceType.OFFICIAL.value: 1,
    SourceType.MAP.value: 2,
    SourceType.WEATHER_API.value: 2,
    SourceType.TRANSIT_API.value: 2,
    SourceType.REVIEW_PLATFORM.value: 3,
    SourceType.FOOD_PLATFORM.value: 4,
    SourceType.LODGING_PLATFORM.value: 4,
    SourceType.WEB.value: 5,
    SourceType.BLOG.value: 6,
    SourceType.SOCIAL.value: 6,
    SourceType.UNKNOWN.value: 7,
}

FIELD_SOURCE_PRIORITY = {
    "opening_hours": [SourceType.OFFICIAL, SourceType.MAP, SourceType.WEB, SourceType.BLOG],
    "ticket_price": [SourceType.OFFICIAL, SourceType.MAP, SourceType.WEB],
    "reservation": [SourceType.OFFICIAL, SourceType.WEB],
    "transit": [SourceType.TRANSIT_API, SourceType.MAP, SourceType.OFFICIAL, SourceType.WEB],
    "weather": [SourceType.WEATHER_API, SourceType.OFFICIAL, SourceType.WEB],
    "review_aspect": [SourceType.REVIEW_PLATFORM, SourceType.MAP, SourceType.WEB, SourceType.BLOG],
    "food": [SourceType.FOOD_PLATFORM, SourceType.MAP, SourceType.REVIEW_PLATFORM],
    "lodging": [SourceType.LODGING_PLATFORM, SourceType.MAP, SourceType.WEB],
}


class SourcePriorityPolicy:
    @staticmethod
    def rank(source_type: SourceType | str) -> int:
        key = source_type.value if isinstance(source_type, SourceType) else source_type
        return SOURCE_PRIORITY.get(key, 7)

    @staticmethod
    def preferred_order(field: str) -> list[SourceType]:
        return FIELD_SOURCE_PRIORITY.get(field, list(SourceType))

    @staticmethod
    def should_prefer(existing_type: SourceType, candidate_type: SourceType) -> bool:
        return SourcePriorityPolicy.rank(candidate_type) < SourcePriorityPolicy.rank(existing_type)


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
    def resolve_conflict_winners(evidence: list, field: str) -> str | None:
        from app.schemas.evidence import ClaimType, Evidence

        claim_type = {
            "opening_hours": ClaimType.OPENING_HOURS,
            "ticket_price": ClaimType.TICKET_PRICE,
        }.get(field)
        if not claim_type:
            return None
        best_source = None
        best_rank = 999
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                if claim.claim_type == claim_type:
                    rank = SourcePriorityPolicy.rank(ev.source_type)
                    if rank < best_rank:
                        best_rank = rank
                        best_source = ev.source_name
        return best_source
