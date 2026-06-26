"""Known / family / generic claim policies for S7 evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.policies.evidence_policy import CLAIM_POLICIES, ClaimPolicy, EvidencePolicy
from app.schemas.evidence import ClaimType, SourceType
from app.schemas.response_contract import ClaimRequirement

CLAIM_TYPE_TO_FAMILY: dict[str, str] = {
    "ticket_price": "ticket_booking",
    "booking_channel": "ticket_booking",
    "historical_ticket_price": "ticket_booking",
    "price_candidate": "ticket_booking",
    "opening_hours": "hard_fact",
    "temporary_closure": "operation_status",
    "reservation_policy": "hard_fact",
    "seasonal_operation_status": "operation_status",
    "road_opening_period": "operation_status",
    "best_time_to_visit": "seasonality_advice",
    "seasonality": "seasonality_advice",
    "general_seasonal_context": "seasonality_advice",
    "weather_today": "live_fact",
    "weather": "live_fact",
    "forecast": "live_fact",
    "current_crowd": "live_fact",
    "crowd_level": "live_fact",
    "queue_time": "live_fact",
    "route_plan": "route_planning",
    "transport_planning": "route_planning",
    "traffic_status": "route_planning",
    "road_traffic": "route_planning",
    "congestion_risk": "route_planning",
    "entity_resolution": "geo_fact",
    "place_lookup": "geo_fact",
    "coordinates": "geo_fact",
    "elevation": "geo_fact",
    "altitude": "geo_fact",
    "height_elevation": "geo_fact",
    "area": "geo_fact",
    "general_fact": "geo_fact",
    "review_summary": "review_experience",
    "value_for_money": "review_experience",
    "elderly_suitability": "suitability_advice",
    "family_friendly": "suitability_advice",
    "commercialization_risk": "review_experience",
    "photo_costume_suitability": "suitability_advice",
    "pet_friendly_suitability": "suitability_advice",
    "nearby_poi": "nearby_recommendation",
    "nearby_food": "nearby_recommendation",
    "nearby_dining": "nearby_recommendation",
    "nearby_restaurant": "nearby_recommendation",
    "nearby_hotel": "nearby_recommendation",
    "nearby_lodging": "nearby_recommendation",
    "nearby_rest_area": "nearby_recommendation",
    "nearby_parking": "nearby_recommendation",
    "nearby_toilet": "nearby_recommendation",
    "nearby_station": "nearby_recommendation",
    "restaurant_recommendation": "nearby_recommendation",
    "comparison": "comparison",
}

CLAIM_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "ticket_price": frozenset(
        {
            ClaimType.TICKET_PRICE.value,
            ClaimType.PRICE_CANDIDATE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            "price_candidate",
            ClaimType.TICKET_RELATED_MENTIONS.value,
        }
    ),
    "opening_hours": frozenset(
        {ClaimType.OPENING_HOURS.value, ClaimType.OPENING_HOURS_CANDIDATE.value}
    ),
    "best_time_to_visit": frozenset(
        {
            ClaimType.BEST_TIME_TO_VISIT.value,
            ClaimType.SEASONALITY.value,
            ClaimType.TRAVEL_ADVICE.value,
        }
    ),
    "seasonality": frozenset({ClaimType.SEASONALITY.value, ClaimType.TRAVEL_ADVICE.value}),
    "review_summary": frozenset(
        {ClaimType.REVIEW_SUMMARY.value, ClaimType.REVIEW_ASPECT.value, "review_aspect"}
    ),
    "value_for_money": frozenset({ClaimType.REVIEW_ASPECT.value, ClaimType.REVIEW_SUMMARY.value}),
    "route_plan": frozenset(
        {ClaimType.ROUTE_STEPS.value, ClaimType.DISTANCE.value, ClaimType.DURATION.value}
    ),
    "entity_resolution": frozenset(
        {ClaimType.PLACE_CANDIDATES.value, ClaimType.COORDINATES.value, ClaimType.POI_UID.value}
    ),
    "elevation": frozenset({ClaimType.ELEVATION.value, ClaimType.TRAVEL_ADVICE.value}),
    "general_fact": frozenset({ClaimType.GENERAL_FACT.value, ClaimType.TRAVEL_ADVICE.value}),
}

# Nearby recommendation needs: aliases registered via nearby_recommendation_policy.claim_aliases_for_need

GEO_ONLY_CLAIMS = frozenset(
    {
        ClaimType.PLACE_CANDIDATES.value,
        ClaimType.COORDINATES.value,
        ClaimType.POI_UID.value,
        ClaimType.RESOLVED_ADDRESS.value,
        ClaimType.ADDRESS.value,
    }
)

IRRELEVANT_FOR: dict[str, frozenset[str]] = {
    "ticket_price": frozenset(
        {
            ClaimType.CROWD.value,
            ClaimType.WEATHER.value,
            *GEO_ONLY_CLAIMS,
            ClaimType.REVIEW_ASPECT.value,
            ClaimType.REVIEW_SUMMARY.value,
            ClaimType.ROUTE_STEPS.value,
        }
    ),
    "opening_hours": frozenset({ClaimType.CROWD.value, ClaimType.WEATHER.value, *GEO_ONLY_CLAIMS}),
    "best_time_to_visit": frozenset(
        {
            ClaimType.CROWD.value,
            ClaimType.TICKET_PRICE.value,
            ClaimType.WEATHER.value,
            *GEO_ONLY_CLAIMS,
            ClaimType.ROUTE_STEPS.value,
        }
    ),
    "seasonality": frozenset({ClaimType.WEATHER.value, ClaimType.TICKET_PRICE.value, *GEO_ONLY_CLAIMS}),
    "review_summary": frozenset(
        {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value, ClaimType.ROUTE_STEPS.value}
    ),
    "value_for_money": frozenset(
        {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value, ClaimType.ROUTE_STEPS.value}
    ),
    "commercialization_risk": frozenset(
        {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value, ClaimType.ROUTE_STEPS.value}
    ),
    "photo_costume_suitability": frozenset(
        {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value, ClaimType.ROUTE_STEPS.value}
    ),
    "route_plan": frozenset({ClaimType.REVIEW_ASPECT.value, ClaimType.TICKET_PRICE.value}),
}

REVIEW_EXPERIENCE_CLAIMS = frozenset(
    {
        "review_summary",
        "value_for_money",
        "elderly_suitability",
        "family_friendly",
        "commercialization_risk",
        "photo_costume_suitability",
        "pet_friendly_suitability",
        "review_aspect",
        ClaimType.REVIEW_ASPECT.value,
    }
)

SOURCE_RELIABILITY: dict[str, float] = {
    "official": 0.95,
    "tourism_board": 0.90,
    "ticketing": 0.75,
    "ticket_platform": 0.75,
    "weather_api": 0.75,
    "map": 0.65,
    "review_platform": 0.55,
    "public_web": 0.50,
    "search_result": 0.45,
    "model_prior": 0.25,
    "fallback": 0.20,
    "mock": 0.20,
}


@dataclass
class ClaimPolicyView:
    claim_type: str
    claim_family: str
    claim_description: str | None
    priority: str
    requires_exact_fact: bool
    requires_live_data: bool
    model_prior_allowed: bool
    estimation_allowed: bool
    preferred_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    allowed_source_types: list[str] = field(default_factory=list)
    coverage_rule: str = ""
    missing_behavior: str = "answer_with_limitation"
    policy_tier: str = "generic"
    claim_aliases: frozenset[str] = field(default_factory=frozenset)
    irrelevant_claim_types: frozenset[str] = field(default_factory=frozenset)
    known_in_registry: bool = False


KNOWN_CLAIM_TYPES = frozenset(
    {
        "ticket_price",
        "opening_hours",
        "temporary_closure",
        "reservation_policy",
        "seasonal_operation_status",
        "road_opening_period",
        "best_time_to_visit",
        "seasonality",
        "route_plan",
        "traffic_status",
        "forecast",
        "current_weather",
        "weather",
        "weather_today",
        "review_summary",
        "value_for_money",
        "nearby_poi",
        "entity_resolution",
        "crowd_level",
        "current_crowd",
    }
)

FAMILY_DEFAULTS: dict[str, dict] = {
    "hard_fact": {
        "requires_exact_fact": True,
        "model_prior_allowed": False,
        "preferred_tools": [
            "official_source_discovery_mcp",
            "official_page_reader_mcp",
            "search_mcp",
            "official",
        ],
    },
    "live_fact": {
        "requires_live_data": True,
        "model_prior_allowed": False,
        "preferred_tools": ["weather_mcp", "openmeteo_mcp", "baidu_weather_mcp"],
    },
    "geo_fact": {
        "preferred_tools": [
            "wikidata_mcp",
            "wikipedia_mcp",
            "search_mcp",
            "browser_mcp",
            "baidu_place_detail_mcp",
            "official_page_reader_mcp",
            "osm_mcp",
        ],
    },
    "ticket_booking": {
        "requires_exact_fact": True,
        "preferred_tools": [
            "official_source_discovery_mcp",
            "official_page_reader_mcp",
            "browser_mcp",
            "search_mcp",
            "baidu_place_detail_mcp",
            "fliggy_ticket_api_mcp",
            "ticketlens_experience_mcp",
            "ctrip_ticket_signal_crawler_mcp",
            "dianping_ticket_signal_crawler_mcp",
            "baidu_place_search_mcp",
        ],
    },
    "operation_status": {
        "requires_exact_fact": True,
        "preferred_tools": ["search_mcp", "official_source_discovery_mcp", "official_page_reader_mcp", "browser_mcp"],
    },
    "seasonality_advice": {
        "model_prior_allowed": True,
        "preferred_tools": ["search_mcp", "knowledge_prior", "climate_mcp"],
    },
    "route_planning": {
        "preferred_tools": ["baidu_route_mcp", "baidu_route_matrix_mcp", "osm_mcp", "transit"],
    },
    "review_experience": {
        "preferred_tools": ["ctrip_review_crawler_mcp", "dianping_review_crawler_mcp", "search_mcp"],
    },
    "nearby_recommendation": {
        "preferred_tools": [
            "baidu_place_search_mcp",
            "baidu_place_detail_mcp",
            "dianping_nearby_crawler_mcp",
            "dianping_review_crawler_mcp",
            "search_mcp",
        ],
    },
    "suitability_advice": {
        "model_prior_allowed": True,
        "preferred_tools": ["search_mcp", "ctrip_review_crawler_mcp", "dianping_review_crawler_mcp"],
    },
    "risk_advice": {
        "preferred_tools": ["search_mcp", "ctrip_review_crawler_mcp"],
    },
    "comparison": {
        "preferred_tools": ["search_mcp", "places_mcp"],
    },
    "open_advice": {
        "model_prior_allowed": True,
        "preferred_tools": ["search_mcp", "knowledge_prior"],
    },
}


def enrich_claim_requirement(claim: ClaimRequirement) -> ClaimRequirement:
    family = claim.claim_family or CLAIM_TYPE_TO_FAMILY.get(claim.claim_type, "open_advice")
    desc = claim.claim_description or claim.claim_type.replace("_", " ")
    if claim.claim_family == family and claim.claim_description == desc:
        return claim
    data = claim.model_dump()
    data["claim_family"] = family
    data["claim_description"] = desc
    return ClaimRequirement.model_validate(data)


def resolve_policy(claim: ClaimRequirement) -> ClaimPolicyView:
    claim = enrich_claim_requirement(claim)
    from app.orchestrator.nearby_recommendation_policy import (
        claim_aliases_for_need,
        is_nearby_information_need,
    )

    if is_nearby_information_need(claim.claim_type):
        aliases = claim_aliases_for_need(claim.claim_type)
    else:
        aliases = CLAIM_TYPE_ALIASES.get(claim.claim_type, frozenset({claim.claim_type}))
    irrelevant = IRRELEVANT_FOR.get(claim.claim_type, frozenset())

    if claim.claim_type in KNOWN_CLAIM_TYPES or claim.claim_type in CLAIM_POLICIES:
        ep: ClaimPolicy = EvidencePolicy.get(claim.claim_type)
        return ClaimPolicyView(
            claim_type=claim.claim_type,
            claim_family=claim.claim_family or "open_advice",
            claim_description=claim.claim_description,
            priority=claim.priority,
            requires_exact_fact=claim.requires_exact_fact or ep.requires_exact_fact,
            requires_live_data=claim.requires_live_data or ep.requires_live_data,
            model_prior_allowed=claim.model_prior_allowed,
            estimation_allowed=claim.estimation_allowed,
            preferred_tools=list(claim.preferred_tools),
            forbidden_tools=list(claim.forbidden_tools),
            allowed_source_types=list(claim.allowed_source_types) or list(ep.preferred_source_types),
            coverage_rule=claim.coverage_rule,
            missing_behavior=claim.missing_behavior,
            policy_tier="known",
            claim_aliases=aliases,
            irrelevant_claim_types=irrelevant,
            known_in_registry=True,
        )

    family = claim.claim_family or "open_advice"
    if family in FAMILY_DEFAULTS:
        defaults = FAMILY_DEFAULTS[family]
        return ClaimPolicyView(
            claim_type=claim.claim_type,
            claim_family=family,
            claim_description=claim.claim_description,
            priority=claim.priority,
            requires_exact_fact=claim.requires_exact_fact or defaults.get("requires_exact_fact", False),
            requires_live_data=claim.requires_live_data or defaults.get("requires_live_data", False),
            model_prior_allowed=claim.model_prior_allowed or defaults.get("model_prior_allowed", False),
            estimation_allowed=claim.estimation_allowed,
            preferred_tools=list(claim.preferred_tools) or list(defaults.get("preferred_tools", [])),
            forbidden_tools=list(claim.forbidden_tools),
            allowed_source_types=list(claim.allowed_source_types),
            coverage_rule=claim.coverage_rule or f"family policy for {family}",
            missing_behavior=claim.missing_behavior,
            policy_tier="family",
            claim_aliases=aliases,
            irrelevant_claim_types=irrelevant,
        )

    return GenericOpenClaimPolicy.from_requirement(claim)


class GenericOpenClaimPolicy:
    @staticmethod
    def from_requirement(claim: ClaimRequirement) -> ClaimPolicyView:
        claim = enrich_claim_requirement(claim)
        return ClaimPolicyView(
            claim_type=claim.claim_type,
            claim_family=claim.claim_family or "open_advice",
            claim_description=claim.claim_description,
            priority=claim.priority,
            requires_exact_fact=claim.requires_exact_fact,
            requires_live_data=claim.requires_live_data,
            model_prior_allowed=claim.model_prior_allowed,
            estimation_allowed=claim.estimation_allowed,
            preferred_tools=list(claim.preferred_tools) or ["search_mcp"],
            forbidden_tools=list(claim.forbidden_tools),
            allowed_source_types=list(claim.allowed_source_types),
            coverage_rule=claim.coverage_rule or "generic open claim",
            missing_behavior=claim.missing_behavior,
            policy_tier="generic",
            claim_aliases=frozenset({claim.claim_type}),
            irrelevant_claim_types=frozenset(),
        )


def source_type_key(source_type, source_name: str | None) -> str:
    st_val = (
        source_type.value
        if isinstance(source_type, SourceType)
        else str(source_type or "").lower()
    )
    name = (source_name or "").lower()
    if source_type == SourceType.OFFICIAL or st_val == "official":
        return "official"
    if source_type == SourceType.MODEL_PRIOR or st_val == "model_prior":
        return "model_prior"
    if "ctrip" in name or "dianping" in name or "fliggy" in name or "ticket" in name:
        return "ticket_platform"
    if "review" in name or "crawler" in name:
        return "review_platform"
    if source_type == SourceType.WEATHER_API or st_val in {"weather_api", "weather"}:
        return "weather_api"
    if source_type in {SourceType.MAP, SourceType.TRANSIT_API} or st_val in {
        "map",
        "transit_api",
        "transit",
    }:
        return "map"
    if source_type == SourceType.TICKET_PLATFORM or st_val == "ticket_platform":
        return "ticket_platform"
    if source_type == SourceType.REVIEW_PLATFORM or st_val == "review_platform":
        return "review_platform"
    if source_type == SourceType.WEB or st_val == "web":
        return "public_web"
    if "search" in name or "websearch" in name:
        return "search_result"
    if st_val == "fallback" or "fallback" in name:
        return "fallback"
    return st_val if st_val in SOURCE_RELIABILITY else "public_web"
