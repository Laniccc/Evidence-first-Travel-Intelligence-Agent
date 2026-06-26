"""Declarative registry: Information Domain → Provider Group → MCP Tool bindings."""

from __future__ import annotations

from app.schemas.s5_information_domain import (
    InformationDomain,
    ProviderGroup,
    S5DomainToolBinding,
    S5ToolRole,
)

D = InformationDomain
P = ProviderGroup
R = S5ToolRole


def _b(
    domain: InformationDomain,
    provider: ProviderGroup,
    tool: str,
    role: S5ToolRole,
    claim_types: list[str],
    *,
    capabilities: list[str] | None = None,
    requires_config: bool = True,
    requires_user_permission: bool = False,
    limitations: list[str] | None = None,
    restrictions: list[str] | None = None,
) -> S5DomainToolBinding:
    return S5DomainToolBinding(
        domain=domain,
        provider_group=provider,
        tool_name=tool,
        role=role,
        capabilities=capabilities or [],
        claim_types=claim_types,
        requires_config=requires_config,
        requires_user_permission=requires_user_permission,
        limitations=limitations or [],
        restrictions=restrictions or [],
    )


_GEO_CLAIMS = [
    "entity_resolution",
    "place_lookup",
    "coordinates",
    "administrative_area",
    "disambiguation",
]

_GEO_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.GEO_RESOLUTION, P.BAIDU_LBS_PROVIDER, "baidu_place_search_mcp", R.PRIMARY, _GEO_CLAIMS),
    _b(D.GEO_RESOLUTION, P.BAIDU_LBS_PROVIDER, "baidu_place_detail_mcp", R.PRIMARY, _GEO_CLAIMS),
    _b(D.GEO_RESOLUTION, P.BAIDU_LBS_PROVIDER, "baidu_geocode_mcp", R.PRIMARY, _GEO_CLAIMS),
    _b(D.GEO_RESOLUTION, P.BAIDU_LBS_PROVIDER, "baidu_reverse_geocode_mcp", R.PRIMARY, _GEO_CLAIMS),
    _b(D.GEO_RESOLUTION, P.SEARCH_PROVIDER, "search_mcp", R.FALLBACK, _GEO_CLAIMS),
]

_GEO_FACT_CLAIMS = [
    "elevation",
    "altitude",
    "height_elevation",
    "mountain_height",
    "peak_height",
    "area",
    "coordinates",
    "general_fact",
]

_GEO_FACT_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.GEO_FACT, P.SEARCH_PROVIDER, "wikidata_mcp", R.PRIMARY, _GEO_FACT_CLAIMS),
    _b(D.GEO_FACT, P.SEARCH_PROVIDER, "wikipedia_mcp", R.PRIMARY, _GEO_FACT_CLAIMS),
    _b(D.GEO_FACT, P.SEARCH_PROVIDER, "search_mcp", R.PRIMARY, _GEO_FACT_CLAIMS),
    _b(D.GEO_FACT, P.CRAWLER_PROVIDER, "browser_mcp", R.PRIMARY, _GEO_FACT_CLAIMS),
    _b(D.GEO_FACT, P.BAIDU_LBS_PROVIDER, "baidu_place_detail_mcp", R.CANDIDATE, _GEO_FACT_CLAIMS),
    _b(D.GEO_FACT, P.OFFICIAL_WEB_PROVIDER, "official_page_reader_mcp", R.CANDIDATE, _GEO_FACT_CLAIMS),
    _b(D.GEO_FACT, P.ROUTE_PROVIDER, "osm_mcp", R.FALLBACK, _GEO_FACT_CLAIMS),
]

_TICKET_CLAIMS = [
    "ticket_price",
    "ticket_price_candidate",
    "ticket_type",
    "discount_policy",
    "reservation_required",
    "booking_channel",
]

_TICKET_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.TICKET_BOOKING, P.OFFICIAL_WEB_PROVIDER, "official_source_discovery_mcp", R.PRIMARY, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.OFFICIAL_WEB_PROVIDER, "official_page_reader_mcp", R.PRIMARY, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.SEARCH_PROVIDER, "search_mcp", R.PRIMARY, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.CRAWLER_PROVIDER, "browser_mcp", R.PRIMARY, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "ticketlens_experience_mcp", R.PRIMARY, _TICKET_CLAIMS),
    _b(
        D.TICKET_BOOKING,
        P.TICKET_PLATFORM_PROVIDER,
        "fliggy_ticket_api_mcp",
        R.PRIMARY,
        _TICKET_CLAIMS,
        limitations=["平台候选价，不等同于官方票价；价格随日期/套餐变化"],
    ),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "fliggy_ticket_snapshot_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "ctrip_ticket_signal_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "dianping_ticket_signal_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.BAIDU_LBS_PROVIDER, "baidu_place_detail_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.FALLBACK_PROVIDER, "ticket_snapshot_store", R.ENRICHMENT, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.FALLBACK_PROVIDER, "ticket_price_history_query", R.ENRICHMENT, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "ctrip_ticket_signal_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "fliggy_ticket_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS, limitations=["deprecated placeholder"]),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "dianping_ticket_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS, limitations=["deprecated placeholder"]),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "meituan_ticket_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(D.TICKET_BOOKING, P.TICKET_PLATFORM_PROVIDER, "qunar_ticket_crawler_mcp", R.CANDIDATE, _TICKET_CLAIMS),
    _b(
        D.TICKET_BOOKING,
        P.MODEL_PRIOR_PROVIDER,
        "knowledge_prior",
        R.FORBIDDEN,
        _TICKET_CLAIMS,
        restrictions=["Hard-fact ticket claims cannot use model prior."],
    ),
]

_OPERATION_CLAIMS = [
    "opening_hours",
    "temporary_closure",
    "reservation_policy",
    "seasonal_operation_status",
    "road_opening_period",
    "daily_notice",
    "capacity_limit",
]

_OPERATION_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.OPERATION_STATUS, P.OFFICIAL_WEB_PROVIDER, "official_page_reader_mcp", R.PRIMARY, _OPERATION_CLAIMS),
    _b(D.OPERATION_STATUS, P.SEARCH_PROVIDER, "search_mcp", R.PRIMARY, _OPERATION_CLAIMS),
    _b(D.OPERATION_STATUS, P.CRAWLER_PROVIDER, "browser_mcp", R.PRIMARY, _OPERATION_CLAIMS),
    _b(D.OPERATION_STATUS, P.BAIDU_LBS_PROVIDER, "baidu_place_detail_mcp", R.CANDIDATE, _OPERATION_CLAIMS),
    _b(D.OPERATION_STATUS, P.BAIDU_LBS_PROVIDER, "baidu_traffic_mcp", R.CANDIDATE, _OPERATION_CLAIMS),
    _b(D.OPERATION_STATUS, P.CRAWLER_PROVIDER, "tourism_board_notice_mcp", R.CANDIDATE, _OPERATION_CLAIMS),
    _b(D.OPERATION_STATUS, P.CRAWLER_PROVIDER, "platform_notice_crawler_mcp", R.CANDIDATE, _OPERATION_CLAIMS),
    _b(
        D.OPERATION_STATUS,
        P.MODEL_PRIOR_PROVIDER,
        "knowledge_prior",
        R.FORBIDDEN,
        _OPERATION_CLAIMS,
        restrictions=["Required hard-fact operation claims cannot use model prior."],
    ),
]

_SEASONALITY_CLAIMS = [
    "best_time_to_visit",
    "seasonality",
    "weather_by_month",
    "scenery_by_month",
    "crowd_by_season",
    "flower_season",
    "snow_season",
    "autumn_foliage",
    "road_condition_by_season",
]

_SEASONALITY_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.SEASONALITY, P.BAIDU_LBS_PROVIDER, "baidu_place_search_mcp", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.BAIDU_LBS_PROVIDER, "baidu_geocode_mcp", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.SEARCH_PROVIDER, "search_mcp", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.CRAWLER_PROVIDER, "browser_mcp", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.WEATHER_PROVIDER, "openmeteo_mcp", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.WEATHER_PROVIDER, "climate_mcp", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.SEARCH_PROVIDER, "seasonality", R.PRIMARY, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.MODEL_PRIOR_PROVIDER, "knowledge_prior", R.FALLBACK, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.FALLBACK_PROVIDER, "fallback", R.FALLBACK, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.CRAWLER_PROVIDER, "mafengwo_note_crawler_mcp", R.CANDIDATE, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.CRAWLER_PROVIDER, "xiaohongshu_note_crawler_mcp", R.CANDIDATE, _SEASONALITY_CLAIMS),
    _b(D.SEASONALITY, P.CRAWLER_PROVIDER, "ctrip_guide_crawler_mcp", R.CANDIDATE, _SEASONALITY_CLAIMS),
]

_ROUTE_CLAIMS = [
    "route_plan",
    "distance",
    "duration",
    "route_steps",
    "walking_distance",
    "transfer_count",
    "drive_time",
    "traffic_status",
    "itinerary_feasibility",
]

_ROUTE_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.ROUTE_PLANNING, P.BAIDU_LBS_PROVIDER, "baidu_place_search_mcp", R.PRIMARY, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.BAIDU_LBS_PROVIDER, "baidu_geocode_mcp", R.PRIMARY, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.BAIDU_LBS_PROVIDER, "baidu_route_mcp", R.PRIMARY, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.BAIDU_LBS_PROVIDER, "baidu_route_matrix_mcp", R.PRIMARY, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.BAIDU_LBS_PROVIDER, "baidu_traffic_mcp", R.PRIMARY, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.ROUTE_PROVIDER, "itinerary_planner_mcp", R.CANDIDATE, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.ROUTE_PROVIDER, "route_feasibility_checker_mcp", R.CANDIDATE, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.ROUTE_PROVIDER, "elderly_friendly_route_scorer_mcp", R.CANDIDATE, _ROUTE_CLAIMS),
    _b(D.ROUTE_PLANNING, P.ROUTE_PROVIDER, "family_trip_planner_mcp", R.CANDIDATE, _ROUTE_CLAIMS),
]

_REVIEW_CLAIMS = [
    "review_summary",
    "positive_aspects",
    "negative_aspects",
    "crowd_risk",
    "queue_risk",
    "commercialization_risk",
    "transport_difficulty",
    "photo_value",
    "family_friendly",
    "elderly_suitability",
    "accessibility_risk",
    "service_quality",
    "scenery_quality",
    "value_for_money",
]

_REVIEW_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "ctrip_review_crawler_mcp", R.PRIMARY, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "dianping_review_crawler_mcp", R.PRIMARY, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.TICKET_PLATFORM_PROVIDER, "ticketlens_experience_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.TICKET_PLATFORM_PROVIDER, "ticketlens_experience_review_signal_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "review_signal_mcp", R.PRIMARY, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "public_review_search_mcp", R.PRIMARY, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "meituan_review_crawler_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "qunar_review_crawler_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.CRAWLER_PROVIDER, "mafengwo_note_crawler_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.CRAWLER_PROVIDER, "xiaohongshu_note_crawler_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.REVIEW_PLATFORM_PROVIDER, "tripadvisor_review_crawler_mcp", R.CANDIDATE, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.SEARCH_PROVIDER, "search_mcp", R.FALLBACK, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.CRAWLER_PROVIDER, "browser_mcp", R.FALLBACK, _REVIEW_CLAIMS),
    _b(D.REVIEW_SIGNAL, P.BAIDU_LBS_PROVIDER, "baidu_place_detail_mcp", R.FALLBACK, _REVIEW_CLAIMS),
]

_NEARBY_CLAIMS = [
    "nearby_poi",
    "restaurant_candidate",
    "rest_area_candidate",
    "hotel_candidate",
    "parking_candidate",
    "toilet_candidate",
    "station_candidate",
    "nearby_attraction",
    "distance",
    "route_duration",
    "rating_candidate",
    "price_level_candidate",
]

_NEARBY_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.NEARBY_RECOMMENDATION, P.BAIDU_LBS_PROVIDER, "baidu_place_search_mcp", R.PRIMARY, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.BAIDU_LBS_PROVIDER, "baidu_place_detail_mcp", R.PRIMARY, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.REVIEW_PLATFORM_PROVIDER, "dianping_nearby_crawler_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.REVIEW_PLATFORM_PROVIDER, "dianping_review_crawler_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.BAIDU_LBS_PROVIDER, "baidu_reverse_geocode_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.CRAWLER_PROVIDER, "nearby_rest_area_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.CRAWLER_PROVIDER, "nearby_toilet_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.CRAWLER_PROVIDER, "nearby_parking_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.CRAWLER_PROVIDER, "nearby_station_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.CRAWLER_PROVIDER, "nearby_attraction_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.CRAWLER_PROVIDER, "nearby_hotel_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.REVIEW_PLATFORM_PROVIDER, "meituan_nearby_crawler_mcp", R.CANDIDATE, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.SEARCH_PROVIDER, "search_mcp", R.FALLBACK, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.FALLBACK_PROVIDER, "restaurant", R.FALLBACK, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.FALLBACK_PROVIDER, "lodging", R.FALLBACK, _NEARBY_CLAIMS),
    _b(D.NEARBY_RECOMMENDATION, P.FALLBACK_PROVIDER, "fallback", R.FALLBACK, _NEARBY_CLAIMS),
]

_REALTIME_CLAIMS = [
    "current_weather",
    "forecast",
    "weather_risk",
    "traffic_status",
    "congestion_risk",
    "current_crowd_estimate",
    "queue_risk",
    "holiday_crowd_risk",
    "event_impact",
]

_REALTIME_BINDINGS: list[S5DomainToolBinding] = [
    _b(D.REALTIME_STATUS, P.WEATHER_PROVIDER, "baidu_weather_mcp", R.PRIMARY, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.WEATHER_PROVIDER, "openmeteo_mcp", R.PRIMARY, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.WEATHER_PROVIDER, "weather_mcp", R.PRIMARY, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.WEATHER_PROVIDER, "weather", R.PRIMARY, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.BAIDU_LBS_PROVIDER, "baidu_traffic_mcp", R.PRIMARY, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.BAIDU_LBS_PROVIDER, "baidu_route_mcp", R.PRIMARY, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.CRAWLER_PROVIDER, "crowd_estimation_mcp", R.CANDIDATE, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.CRAWLER_PROVIDER, "event_calendar_mcp", R.CANDIDATE, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.REVIEW_PLATFORM_PROVIDER, "dianping_review_crawler_mcp", R.CANDIDATE, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.REVIEW_PLATFORM_PROVIDER, "ctrip_review_crawler_mcp", R.CANDIDATE, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.SEARCH_PROVIDER, "search_mcp", R.FALLBACK, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.CRAWLER_PROVIDER, "browser_mcp", R.FALLBACK, _REALTIME_CLAIMS),
    _b(D.REALTIME_STATUS, P.FALLBACK_PROVIDER, "fallback", R.FALLBACK, _REALTIME_CLAIMS),
    _b(
        D.REALTIME_STATUS,
        P.MODEL_PRIOR_PROVIDER,
        "knowledge_prior",
        R.FORBIDDEN,
        _REALTIME_CLAIMS,
        restrictions=["Live realtime facts cannot use model prior."],
    ),
]

S5_INFORMATION_DOMAIN_REGISTRY: dict[InformationDomain, list[S5DomainToolBinding]] = {
    D.GEO_RESOLUTION: _GEO_BINDINGS,
    D.GEO_FACT: _GEO_FACT_BINDINGS,
    D.TICKET_BOOKING: _TICKET_BINDINGS,
    D.OPERATION_STATUS: _OPERATION_BINDINGS,
    D.SEASONALITY: _SEASONALITY_BINDINGS,
    D.ROUTE_PLANNING: _ROUTE_BINDINGS,
    D.REVIEW_SIGNAL: _REVIEW_BINDINGS,
    D.NEARBY_RECOMMENDATION: _NEARBY_BINDINGS,
    D.REALTIME_STATUS: _REALTIME_BINDINGS,
}

_PLACEHOLDER_TOOLS: frozenset[str] = frozenset(
    {
        "fliggy_ticket_crawler_mcp",
        "meituan_ticket_crawler_mcp",
        "dianping_ticket_crawler_mcp",
        "qunar_ticket_crawler_mcp",
        "tourism_board_notice_mcp",
        "platform_notice_crawler_mcp",
        "mafengwo_note_crawler_mcp",
        "xiaohongshu_note_crawler_mcp",
        "review_signal_mcp",
        "public_review_search_mcp",
        "meituan_review_crawler_mcp",
        "tripadvisor_review_crawler_mcp",
        "nearby_food_mcp",
        "nearby_rest_area_mcp",
        "nearby_toilet_mcp",
        "nearby_parking_mcp",
        "nearby_station_mcp",
        "nearby_attraction_mcp",
        "nearby_hotel_mcp",
        "meituan_nearby_crawler_mcp",
        "itinerary_planner_mcp",
        "route_feasibility_checker_mcp",
        "elderly_friendly_route_scorer_mcp",
        "family_trip_planner_mcp",
        "event_calendar_mcp",
    }
)


def bindings_for_domain(domain: InformationDomain) -> list[S5DomainToolBinding]:
    return list(S5_INFORMATION_DOMAIN_REGISTRY.get(domain, []))


def all_registered_tool_names() -> set[str]:
    names: set[str] = set()
    for bindings in S5_INFORMATION_DOMAIN_REGISTRY.values():
        for binding in bindings:
            names.add(binding.tool_name)
    return names


def placeholder_tool_names() -> set[str]:
    return set(_PLACEHOLDER_TOOLS)


def provider_groups_for_domains(domains: list[InformationDomain]) -> list[ProviderGroup]:
    seen: list[ProviderGroup] = []
    for domain in domains:
        for binding in bindings_for_domain(domain):
            if binding.provider_group not in seen:
                seen.append(binding.provider_group)
    return seen
