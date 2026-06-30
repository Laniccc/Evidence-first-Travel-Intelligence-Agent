"""Authoritative claim_family metadata for lookup / evidence goal layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.evidence import ClaimType

CLAIM_TYPE_TO_FAMILY: dict[str, str] = {
    # entity_identity
    "place_identity": "entity_identity",
    "canonical_place_name": "entity_identity",
    "official_source_candidate": "entity_identity",
    "official_website": "entity_identity",
    # operation_status
    "opening_hours": "operation_status",
    "seasonal_opening_hours": "operation_status",
    "last_entry_time": "operation_status",
    "last_ticket_time": "operation_status",
    "closed_days": "operation_status",
    "current_open_status": "operation_status",
    "temporary_closure": "operation_status",
    "special_opening_notice": "operation_status",
    "operation_season": "operation_status",
    "seasonal_operation_status": "operation_status",
    "road_opening_period": "operation_status",
    # ticket_booking
    "ticket_price": "ticket_booking",
    "entrance_ticket_price": "ticket_booking",
    "ticket_product_price": "ticket_booking",
    "boat_ticket_price": "ticket_booking",
    "shuttle_bus_ticket_price": "ticket_booking",
    "cable_car_ticket_price": "ticket_booking",
    "combo_ticket_price": "ticket_booking",
    "booking_channel": "ticket_booking",
    "historical_ticket_price": "ticket_booking",
    "price_candidate": "ticket_booking",
    "reservation_policy": "ticket_booking",
    "reservation_requirement": "rule_policy",
    # geo_fact
    "entity_resolution": "geo_fact",
    "place_lookup": "geo_fact",
    "coordinates": "geo_fact",
    "elevation": "geo_fact",
    "highest_peak_elevation": "geo_fact",
    "main_peak_elevations": "geo_fact",
    "altitude": "geo_fact",
    "height_elevation": "geo_fact",
    "area": "geo_fact",
    "general_fact": "geo_fact",
    "address": "geo_fact",
    # transport_access
    "transport_access": "transport_access",
    "parking_availability": "transport_access",
    "nearest_station": "transport_access",
    "shuttle_bus_availability": "transport_access",
    "traffic_restriction": "transport_access",
    "road_open_status": "transport_access",
    "estimated_travel_time": "transport_access",
    "route_plan": "transport_access",
    "transit": "transport_access",
    # facility_service
    "restaurant_availability": "facility_service",
    "lodging_availability": "facility_service",
    "toilet_availability": "facility_service",
    "nearby_poi": "facility_service",
    "nearby_food": "facility_service",
    "nearby_toilet": "facility_service",
    "nearby_parking": "facility_service",
    # rule_policy
    "entry_requirement": "rule_policy",
    "pet_policy": "rule_policy",
    "reservation_policy": "rule_policy",
    # realtime_notice
    "weather_today": "realtime_notice",
    "weather": "realtime_notice",
    "forecast": "realtime_notice",
    "crowd_level": "realtime_notice",
    "current_crowd": "realtime_notice",
    "queue_time": "realtime_notice",
    "official_notice": "realtime_notice",
    # legacy / advisory families
    "best_time_to_visit": "seasonality_advice",
    "seasonality": "seasonality_advice",
    "winter_visit_suitability": "seasonality_advice",
    "transport_difficulty": "transport_access",
    "weather_risk": "realtime_notice",
    "review_summary": "review_experience",
    "value_for_money": "review_experience",
    "comparison": "comparison",
    "general_travel_advice": "suitability_advice",
}

_TICKET_BOOKING_TYPES = frozenset(
    {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
        "combo_ticket_price",
        "ticket_product_price",
    }
)


@dataclass(frozen=True)
class ClaimFamilySpec:
    claim_family: str
    extraction_schema: str | None = None
    default_source_families: tuple[str, ...] = ()
    claim_types: tuple[str, ...] = ()


FAMILY_SPECS: dict[str, ClaimFamilySpec] = {
    "entity_identity": ClaimFamilySpec(
        claim_family="entity_identity",
        default_source_families=("geo_resolution", "search"),
        claim_types=("place_identity", "official_source_candidate", "official_website"),
    ),
    "operation_status": ClaimFamilySpec(
        claim_family="operation_status",
        extraction_schema="OpeningHoursFact",
        default_source_families=(
            "official_source",
            "official_page_reader",
            "search",
            "map_candidate",
        ),
        claim_types=("opening_hours", "temporary_closure", "current_open_status"),
    ),
    "ticket_booking": ClaimFamilySpec(
        claim_family="ticket_booking",
        extraction_schema="TicketPriceFact",
        default_source_families=("official_source", "ticket_platform", "search"),
        claim_types=_TICKET_BOOKING_TYPES,
    ),
    "geo_fact": ClaimFamilySpec(
        claim_family="geo_fact",
        default_source_families=("geo_authority", "search", "map_candidate"),
        claim_types=("elevation", "highest_peak_elevation", "coordinates", "address"),
    ),
    "transport_access": ClaimFamilySpec(
        claim_family="transport_access",
        default_source_families=("map_candidate", "search"),
        claim_types=("parking_availability", "road_open_status", "transport_access"),
    ),
    "facility_service": ClaimFamilySpec(
        claim_family="facility_service",
        default_source_families=("map_candidate", "nearby"),
        claim_types=("toilet_availability", "restaurant_availability"),
    ),
    "rule_policy": ClaimFamilySpec(
        claim_family="rule_policy",
        default_source_families=("official_source", "official_page_reader"),
        claim_types=("reservation_requirement", "pet_policy", "entry_requirement"),
    ),
    "realtime_notice": ClaimFamilySpec(
        claim_family="realtime_notice",
        default_source_families=("live_api", "search"),
        claim_types=("crowd_status", "weather_alert", "official_notice"),
    ),
}

_PREFERRED_TOOLS: dict[str, list[str]] = {
    "opening_hours": [
        "search_mcp",
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "browser_mcp",
        "baidu_place_detail_mcp",
    ],
    "ticket_price": [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "fliggy_ticket_api_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "search_mcp",
    ],
    "entrance_ticket_price": [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "fliggy_ticket_api_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "search_mcp",
    ],
    "boat_ticket_price": [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "fliggy_ticket_api_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "search_mcp",
    ],
    "shuttle_bus_ticket_price": [
        "official_page_reader_mcp",
        "search_mcp",
        "baidu_place_detail_mcp",
    ],
    "cable_car_ticket_price": [
        "official_page_reader_mcp",
        "search_mcp",
        "baidu_place_detail_mcp",
    ],
    "elevation": ["wikidata_mcp", "wikipedia_mcp", "search_mcp", "baidu_place_detail_mcp"],
    "highest_peak_elevation": ["wikidata_mcp", "wikipedia_mcp", "search_mcp"],
    "road_open_status": ["search_mcp", "official_page_reader_mcp", "baidu_place_detail_mcp"],
}


def claim_family_for_type(claim_type: str) -> str:
    return CLAIM_TYPE_TO_FAMILY.get(claim_type, "geo_fact")


def family_spec(claim_family: str) -> ClaimFamilySpec | None:
    return FAMILY_SPECS.get(claim_family)


def preferred_source_families_for(claim_type: str) -> list[str]:
    family = claim_family_for_type(claim_type)
    spec = FAMILY_SPECS.get(family)
    if not spec:
        return ["search"]
    return list(spec.default_source_families)


def preferred_tools_for_claim(claim_type: str) -> list[str]:
    if claim_type in _PREFERRED_TOOLS:
        return list(_PREFERRED_TOOLS[claim_type])
    if claim_type in _TICKET_BOOKING_TYPES:
        return list(_PREFERRED_TOOLS.get("ticket_price", ["search_mcp"]))
    if claim_family_for_type(claim_type) == "operation_status":
        return list(_PREFERRED_TOOLS["opening_hours"])
    return ["search_mcp"]


def extraction_schema_for(claim_type: str) -> str | None:
    spec = FAMILY_SPECS.get(claim_family_for_type(claim_type))
    return spec.extraction_schema if spec else None


def ticket_claim_types() -> frozenset[str]:
    return _TICKET_BOOKING_TYPES


# Re-export aliases used by claim_policy_registry
CLAIM_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "ticket_price": frozenset(
        {
            ClaimType.TICKET_PRICE.value,
            ClaimType.PRICE_CANDIDATE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            "price_candidate",
            ClaimType.TICKET_RELATED_MENTIONS.value,
            "entrance_ticket_price",
            "boat_ticket_price",
        }
    ),
    "boat_ticket_price": frozenset(
        {
            ClaimType.TICKET_PRICE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            "boat_ticket_price",
        }
    ),
    "entrance_ticket_price": frozenset(
        {
            ClaimType.TICKET_PRICE.value,
            ClaimType.TICKET_PRICE_CANDIDATE.value,
            "entrance_ticket_price",
            "ticket_price",
        }
    ),
    "opening_hours": frozenset(
        {ClaimType.OPENING_HOURS.value, ClaimType.OPENING_HOURS_CANDIDATE.value}
    ),
    "elevation": frozenset({ClaimType.ELEVATION.value, ClaimType.TRAVEL_ADVICE.value}),
    "general_fact": frozenset({ClaimType.GENERAL_FACT.value, ClaimType.TRAVEL_ADVICE.value}),
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
}
