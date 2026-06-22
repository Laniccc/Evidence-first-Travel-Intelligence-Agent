from pydantic import BaseModel, Field


class ClaimPolicy(BaseModel):
    model_prior_allowed: bool = False
    required_source_types: list[str] = Field(default_factory=list)
    preferred_source_types: list[str] = Field(default_factory=list)
    allowed_estimation_sources: list[str] = Field(default_factory=list)
    requires_live_data: bool = False
    requires_exact_fact: bool = False


CLAIM_POLICIES: dict[str, ClaimPolicy] = {
    "opening_hours": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["official", "map"],
        requires_exact_fact=True,
    ),
    "ticket_price": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["official", "ticketing"],
        requires_exact_fact=True,
    ),
    "weather_today": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["weather_api"],
        requires_live_data=True,
        requires_exact_fact=True,
    ),
    "weather": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["weather_api"],
        requires_live_data=True,
    ),
    "current_crowd": ClaimPolicy(
        model_prior_allowed=False,
        allowed_estimation_sources=["review", "map_proxy", "event"],
        requires_live_data=True,
    ),
    "crowd_level": ClaimPolicy(
        model_prior_allowed=False,
        allowed_estimation_sources=["review", "map_proxy", "event"],
    ),
    "best_time_to_visit": ClaimPolicy(
        model_prior_allowed=True,
        preferred_source_types=["climate_api", "tourism_board", "model_prior"],
    ),
    "seasonality": ClaimPolicy(
        model_prior_allowed=True,
        preferred_source_types=["climate_api", "tourism_board", "model_prior"],
    ),
    "climate_monthly": ClaimPolicy(
        model_prior_allowed=False,
        preferred_source_types=["climate_api", "weather_api"],
    ),
    "monthly_weather": ClaimPolicy(
        model_prior_allowed=False,
        preferred_source_types=["climate_api", "weather_api"],
    ),
    "public_web_search": ClaimPolicy(
        model_prior_allowed=False,
        preferred_source_types=["web", "tourism_board"],
    ),
    "entity_resolution": ClaimPolicy(
        model_prior_allowed=False,
        preferred_source_types=["wikidata", "map"],
    ),
    "official_page_read": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["official"],
        requires_exact_fact=True,
    ),
    "seasonal_events": ClaimPolicy(model_prior_allowed=True, preferred_source_types=["web", "tourism_board"]),
    "snow_season": ClaimPolicy(model_prior_allowed=True, preferred_source_types=["climate_api", "web"]),
    "autumn_foliage": ClaimPolicy(model_prior_allowed=True, preferred_source_types=["climate_api", "web"]),
    "flower_season": ClaimPolicy(model_prior_allowed=True, preferred_source_types=["climate_api", "web"]),
    "crowd_by_season": ClaimPolicy(model_prior_allowed=True, preferred_source_types=["review", "web"]),
    "nearby_poi": ClaimPolicy(model_prior_allowed=False, preferred_source_types=["map"]),
    "price_candidate": ClaimPolicy(
        model_prior_allowed=False,
        allowed_estimation_sources=["map"],
        requires_exact_fact=False,
    ),
    "opening_hours_candidate": ClaimPolicy(
        model_prior_allowed=False,
        allowed_estimation_sources=["map"],
        requires_exact_fact=False,
    ),
    "general_travel_advice": ClaimPolicy(
        model_prior_allowed=True,
        preferred_source_types=["web", "tourism_board", "wikidata", "model_prior"],
    ),
    "fallback_web_lookup": ClaimPolicy(
        model_prior_allowed=True,
        preferred_source_types=["web", "model_prior"],
    ),
    "reservation_policy": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["official"],
        requires_exact_fact=True,
    ),
    "transit": ClaimPolicy(
        model_prior_allowed=False,
        preferred_source_types=["transit_api", "map"],
    ),
    "seasonal_operation_status": ClaimPolicy(
        model_prior_allowed=False,
        required_source_types=["official", "public_web", "tourism_board"],
        requires_exact_fact=True,
    ),
    "general_seasonal_context": ClaimPolicy(
        model_prior_allowed=True,
        preferred_source_types=["model_prior", "web", "climate_api"],
    ),
}


FORBIDDEN_MODEL_PRIOR_CLAIMS = frozenset(
    {
        "opening_hours",
        "ticket_price",
        "weather_today",
        "weather",
        "current_crowd",
        "crowd_level",
        "reservation_policy",
        "seasonal_operation_status",
    }
)


class EvidencePolicy:
    @classmethod
    def get(cls, need_key: str) -> ClaimPolicy:
        return CLAIM_POLICIES.get(need_key, ClaimPolicy(model_prior_allowed=False))

    @classmethod
    def model_prior_allowed_for(cls, need_key: str) -> bool:
        return cls.get(need_key).model_prior_allowed

    @classmethod
    def requires_evidence_for(cls, need_key: str) -> bool:
        policy = cls.get(need_key)
        return not policy.model_prior_allowed or policy.requires_exact_fact or policy.requires_live_data

    @classmethod
    def forbidden_model_prior_claims(cls) -> frozenset[str]:
        return FORBIDDEN_MODEL_PRIOR_CLAIMS
