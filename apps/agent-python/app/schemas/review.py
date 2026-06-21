from enum import Enum

from pydantic import BaseModel, Field


class ReviewAspectName(str, Enum):
    CROWD_LEVEL = "crowd_level"
    QUEUE_TIME = "queue_time"
    PHOTO_EXPERIENCE = "photo_experience"
    FAMILY_FRIENDLINESS = "family_friendliness"
    ELDERLY_FRIENDLINESS = "elderly_friendliness"
    ACCESSIBILITY = "accessibility"
    WALKING_INTENSITY = "walking_intensity"
    CLEANLINESS = "cleanliness"
    SERVICE_QUALITY = "service_quality"
    VALUE_FOR_MONEY = "value_for_money"
    TRANSPORT_CONVENIENCE = "transport_convenience"
    FOOD_NEARBY = "food_nearby"
    SAFETY = "safety"
    WEATHER_SENSITIVITY = "weather_sensitivity"
    COMMERCIALIZATION = "commercialization"
    OVERRATED_RISK = "overrated_risk"
    FIRST_TIMER_FIT = "first_timer_fit"


class ReviewInputItem(BaseModel):
    source: str
    rating: float | None = None
    text: str
    language: str = "unknown"
    published_at: str | None = None


class ReviewInput(BaseModel):
    place_name: str
    reviews: list[ReviewInputItem] = Field(default_factory=list)
    user_profile: dict = Field(default_factory=dict)


class ReviewAspect(BaseModel):
    aspect: ReviewAspectName
    sentiment: str
    severity: str = "unknown"
    frequency: float = 0.0
    recent_trend: str = "unknown"
    evidence_examples: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class PersonaImplication(BaseModel):
    persona: str
    fit: str
    reason: str


class ReviewAspectResult(BaseModel):
    place_name: str
    review_summary: str
    aspects: list[ReviewAspect] = Field(default_factory=list)
    persona_implications: list[PersonaImplication] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
