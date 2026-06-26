from enum import Enum

from pydantic import BaseModel, Field


class InformationNeedType(str, Enum):
    OPENING_HOURS = "opening_hours"
    TICKET_PRICE = "ticket_price"
    RESERVATION_POLICY = "reservation_policy"
    TEMPORARY_CLOSURE = "temporary_closure"
    CROWD_LEVEL = "crowd_level"
    QUEUE_TIME = "queue_time"
    WALKING_INTENSITY = "walking_intensity"
    ACCESSIBILITY = "accessibility"
    WEATHER = "weather"
    TRANSIT = "transit"
    NEARBY_FOOD = "nearby_food"
    NEARBY_REST_AREA = "nearby_rest_area"
    LOCKER = "locker"
    STROLLER_FRIENDLINESS = "stroller_friendliness"
    PHOTO_SPOT = "photo_spot"
    SAFETY = "safety"
    EVENT = "event"
    FALLBACK_WEB_LOOKUP = "fallback_web_lookup"
    # General factual attributes about places
    ELEVATION = "elevation"
    GENERAL_FACT = "general_fact"


class NeedPriority(str, Enum):
    REQUIRED = "required"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InformationNeed(BaseModel):
    need_type: InformationNeedType
    priority: NeedPriority = NeedPriority.MEDIUM
    place: str | None = None
    city: str | None = None
    date: str | None = None
    reason: str = ""
    acceptable_staleness: str = "recent"
    fallback_allowed: bool = True
