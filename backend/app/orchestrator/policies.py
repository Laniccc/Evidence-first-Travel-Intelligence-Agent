from app.schemas.evidence import SourceType

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
