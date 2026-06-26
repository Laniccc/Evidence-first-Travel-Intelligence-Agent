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
    TICKET_PLATFORM = "ticket_platform"
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
    BEST_TIME_TO_VISIT = "best_time_to_visit"
    PLACE_CANDIDATES = "place_candidates"
    OPENING_HOURS_CANDIDATE = "opening_hours_candidate"
    PRICE_CANDIDATE = "price_candidate"
    RATING_CANDIDATE = "rating_candidate"
    POI_UID = "poi_uid"
    COORDINATES = "coordinates"
    SEASONAL_OPERATION_STATUS = "seasonal_operation_status"
    GENERAL_SEASONAL_CONTEXT = "general_seasonal_context"
    ROAD_OPENING_PERIOD = "road_opening_period"
    PUBLIC_NOTICE = "public_notice"
    ROUTE_STEPS = "route_steps"
    DISTANCE = "distance"
    DURATION = "duration"
    TRAFFIC_STATUS = "traffic_status"
    CONGESTION_RISK = "congestion_risk"
    INFERRED_CITY = "inferred_city"
    USER_LOCATION_ESTIMATION = "user_location_estimation"
    RESOLVED_ADDRESS = "resolved_address"
    TICKET_PRICE_CANDIDATE = "ticket_price_candidate"
    BOOKING_CHANNEL = "booking_channel"
    ACTIVITY_PRICE = "activity_price"
    TICKET_TYPE = "ticket_type"
    SALES_STATUS = "sales_status"
    REVIEW_SUMMARY = "review_summary"
    TICKET_RELATED_MENTIONS = "ticket_related_mentions"
    HISTORICAL_TICKET_SNAPSHOT = "historical_ticket_snapshot"
    TICKET_PRICE_HISTORY = "ticket_price_history"
    PLATFORM_TICKET_URL = "platform_ticket_url"
    REVIEW_COUNT = "review_count"
    OFFICIAL_SOURCE_CANDIDATE = "official_source_candidate"
    # General factual attributes about places (elevation, area, founding year, etc.)
    ELEVATION = "elevation"
    GENERAL_FACT = "general_fact"


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
