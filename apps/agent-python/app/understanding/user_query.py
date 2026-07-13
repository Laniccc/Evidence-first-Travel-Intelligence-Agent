"""User query and goal models owned by the understanding layer."""

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    SINGLE_PLACE = "single_place"
    COMPARE_PLACES = "compare_places"
    ITINERARY = "itinerary"
    TRANSPORT = "transport"
    FOOD_LODGING = "food_lodging"
    WEATHER_RISK = "weather_risk"
    GENERAL = "general"


class PartyType(str, Enum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    ELDERLY = "elderly"
    CHILDREN = "children"
    FRIENDS = "friends"


class BudgetLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class PaceType(str, Enum):
    RELAXED = "relaxed"
    NORMAL = "normal"
    INTENSE = "intense"
    UNKNOWN = "unknown"


class TransportPreference(str, Enum):
    PUBLIC_TRANSPORT = "public_transport"
    TAXI = "taxi"
    WALKING = "walking"
    DRIVING = "driving"
    UNKNOWN = "unknown"


class UserContext(BaseModel):
    travel_date: str | None = None
    party: list[PartyType] = Field(default_factory=list)
    pace: PaceType = PaceType.UNKNOWN
    transport_preference: TransportPreference = TransportPreference.UNKNOWN
    budget_level: BudgetLevel = BudgetLevel.UNKNOWN
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    start_location: str | None = None
    location_usage_allowed: bool = False


class UserGoal(BaseModel):
    intent_type: IntentType = IntentType.GENERAL
    destination_country: str | None = None
    destination_city: str | None = None
    place_candidates: list[str] = Field(default_factory=list)
    travel_date: str | None = None
    start_location: str | None = None
    party: list[PartyType] = Field(default_factory=list)
    budget_level: BudgetLevel = BudgetLevel.UNKNOWN
    pace: PaceType = PaceType.UNKNOWN
    transport_preference: TransportPreference = TransportPreference.UNKNOWN
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class RegionGateResult(BaseModel):
    supported: bool
    country: str | None = None
    city: str | None = None
    reason: str = ""


__all__ = [
    "BudgetLevel",
    "IntentType",
    "PaceType",
    "PartyType",
    "RegionGateResult",
    "TransportPreference",
    "UserContext",
    "UserGoal",
]
