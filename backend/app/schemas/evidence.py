from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    OFFICIAL = "official"
    MAP = "map"
    REVIEW_PLATFORM = "review_platform"
    WEATHER_API = "weather_api"
    TRANSIT_API = "transit_api"
    FOOD_PLATFORM = "food_platform"
    LODGING_PLATFORM = "lodging_platform"
    WEB = "web"
    BLOG = "blog"
    SOCIAL = "social"
    MODEL_PRIOR = "model_prior"
    UNKNOWN = "unknown"


class LicenseScope(str, Enum):
    API_ALLOWED = "api_allowed"
    PUBLIC_PAGE = "public_page"
    USER_PROVIDED = "user_provided"
    UNKNOWN = "unknown"


class DataFreshness(str, Enum):
    LIVE = "live"
    RECENT = "recent"
    STALE = "stale"
    UNKNOWN = "unknown"


class ClaimType(str, Enum):
    OPENING_HOURS = "opening_hours"
    TICKET_PRICE = "ticket_price"
    RESERVATION = "reservation"
    ADDRESS = "address"
    TRANSIT = "transit"
    REVIEW_ASPECT = "review_aspect"
    WEATHER = "weather"
    CROWD = "crowd"
    FOOD = "food"
    LODGING = "lodging"
    SAFETY = "safety"
    ACCESSIBILITY = "accessibility"
    TRAVEL_ADVICE = "travel_advice"
    SEASONALITY = "seasonality"


class Claim(BaseModel):
    claim_type: ClaimType
    value: Any
    raw_text: str | None = None
    normalized_value: Any = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    source_name: str
    source_type: SourceType
    source_url: str | None = None
    country: str
    city: str | None = None
    place_name: str | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: datetime | None = None
    data_freshness: DataFreshness = DataFreshness.RECENT
    license_scope: LicenseScope = LicenseScope.PUBLIC_PAGE
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    claims: list[Claim] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
