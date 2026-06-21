from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.place_context import PlaceContext
from app.schemas.user_profile import UserProfile


class TravelTaskType(str, Enum):
    SINGLE_PLACE_SUITABILITY = "single_place_suitability"
    PLACE_FACT_LOOKUP = "place_fact_lookup"
    COMPARE_PLACES = "compare_places"
    ITINERARY_PLANNING = "itinerary_planning"
    CROWD_INQUIRY = "crowd_inquiry"
    WEATHER_RISK = "weather_risk"
    TRANSPORT_PLANNING = "transport_planning"
    FOOD_NEARBY = "food_nearby"
    LODGING_AREA = "lodging_area"
    OPEN_ENDED_ADVICE = "open_ended_advice"


class TravelTask(BaseModel):
    task_type: TravelTaskType = TravelTaskType.OPEN_ENDED_ADVICE
    rewritten_query: str = ""
    country: str | None = None
    city: str | None = None
    places: list[PlaceContext] = Field(default_factory=list)
    travel_date: str | None = None
    start_location: str | None = None
    user_profile: UserProfile | None = None
    key_concerns: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    optional_evidence: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    followup_context_used: bool = False
    confidence: float = 0.8
