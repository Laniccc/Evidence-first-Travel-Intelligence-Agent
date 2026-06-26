from __future__ import annotations

import re

from app.config import get_settings
from app.orchestrator.comparison_helpers import is_comparison_mode
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.orchestrator.state_policy import EVIDENCE_PLANNING_TOOL_NAMES
from app.orchestrator.s5_information_domain_registry import placeholder_tool_names
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.s5_information_domain import S5DomainPlan
from app.schemas.semantic_frame import AnswerMode, DecisionType, QueryScope, SemanticFrame
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry
from app.tools.mcp.client_manager import get_mcp_client_manager
from app.tools.mcp.tool_specs import MCP_POLICY_SPECS, MCP_POLICY_TOOL_NAMES, NEED_TOOL_PROFILES
from app.tools.mcp.adapter_status import (
    is_mcp_policy_implemented,
    is_mcp_policy_placeholder,
    mcp_policy_stub_reason,
)
from tools.ticketing.provider_config import (
    TICKET_PROVIDER_TOOL_NAMES,
    fliggy_api_block_reason,
    is_crowd_provider_tool,
    is_ticket_provider_tool,
    provider_configured_for_tool,
    provider_enabled_for_tool,
)
from app.tools.gateway_config import use_java_tool_gateway
from app.tools.tool_name_resolver import is_mcp_policy_tool, resolve_tool_name

_HARD_FACT_NEEDS = frozenset(
    {
        "opening_hours",
        "ticket_price",
        "weather_today",
        "today_weather",
        "forecast",
        "current_crowd",
        "queue_time",
        "temporary_closure",
        "reservation_policy",
    }
)

_PLACE_VALIDATION_TOOLS = frozenset(
    {"osm_mcp", "places_mcp", "wikidata_mcp", "baidu_place_search_mcp"}
)

_GEO_FACT_ELEVATION_ALLOWLIST = frozenset(
    {
        "search_mcp",
        "browser_mcp",
        "wikipedia_mcp",
        "wikidata_mcp",
        "official_page_reader_mcp",
        "official_source_discovery_mcp",
        "baidu_place_detail_mcp",
        "baidu_place_search_mcp",
        "baidu_geocode_mcp",
        "osm_mcp",
        "entity_resolution_agent",
        "fact_lookup_agent",
        "fact_search_agent",
    }
)

_ELEVATION_CLAIM_TYPES = frozenset(
    {
        "elevation",
        "altitude",
        "height_elevation",
        "highest_peak_elevation",
        "main_peak_elevations",
    }
)


def _contract_is_geo_fact_elevation(contract) -> bool:
    types = {c.claim_type for c in contract.claim_requirements}
    if not types & _ELEVATION_CLAIM_TYPES:
        return False
    non_geo = types - _ELEVATION_CLAIM_TYPES - {"entity_resolution"}
    return not non_geo

_BAIDU_DISAMBIGUATION_NEEDS = frozenset(
    {"best_time_to_visit", "seasonality", "entity_resolution"}
)

_CAPABILITY_TO_POLICY: dict[str, str] = {
    "official": "official",
    "real_official_page_tool": "official",
    "mock_official_tool": "official",
    "official_reader_mcp": "official_page_reader_mcp",
    "official_page_reader_mcp": "official_page_reader_mcp",
    "places": "places",
    "real_places_tool": "places",
    "mock_places_tool": "places",
    "places_mcp": "places_mcp",
    "osm_mcp": "osm_mcp",
    "geocode_mcp": "geocode_mcp",
    "weather": "weather",
    "real_weather_tool": "weather",
    "mock_weather_tool": "weather",
    "weather_mcp": "weather_mcp",
    "openmeteo_mcp": "openmeteo_mcp",
    "climate_mcp": "climate_mcp",
    "search_mcp": "search_mcp",
    "browser_mcp": "browser_mcp",
    "wikipedia_mcp": "wikipedia_mcp",
    "wikidata_mcp": "wikidata_mcp",
    "sqlite_mcp": "sqlite_mcp",
    "evidence_store_mcp": "evidence_store_mcp",
    "baidu_place_search_mcp": "baidu_place_search_mcp",
    "baidu_place_detail_mcp": "baidu_place_detail_mcp",
    "baidu_weather_mcp": "baidu_weather_mcp",
    "baidu_geocode_mcp": "baidu_geocode_mcp",
    "baidu_reverse_geocode_mcp": "baidu_reverse_geocode_mcp",
    "baidu_route_mcp": "baidu_route_mcp",
    "baidu_route_matrix_mcp": "baidu_route_matrix_mcp",
    "baidu_traffic_mcp": "baidu_traffic_mcp",
    "baidu_ip_location_mcp": "baidu_ip_location_mcp",
    "reviews": "reviews",
    "transit": "transit",
    "restaurant": "restaurant",
    "lodging": "lodging",
    "fallback": "fallback",
    "seasonality": "seasonality",
}

_TOOL_CATALOG: dict[str, dict] = {
    "official": {
        "description": "Official site / ticketing pages for hours, prices, reservation policy.",
        "capabilities": ["opening_hours", "ticket_price", "reservation_policy", "temporary_closure"],
        "source_type": "official",
    },
    "places": {
        "description": "Map / POI data for address, opening status, crowd proxy.",
        "capabilities": ["address", "opening_status", "crowd_level", "nearby_poi"],
        "source_type": "map",
    },
    "weather": {
        "description": "Weather and climate API for travel-date or seasonal risk.",
        "capabilities": ["weather", "weather_risk", "monthly_weather"],
        "source_type": "weather_api",
        "requires_api_key": True,
    },
    "reviews": {
        "description": "Review mining for crowd, queue, accessibility proxies.",
        "capabilities": ["crowd_level", "queue_time"],
        "source_type": "review",
    },
    "transit": {
        "description": "Transit and walking intensity summaries.",
        "capabilities": ["transit"],
        "source_type": "transit",
    },
    "restaurant": {
        "description": "Nearby food and rest-area suggestions.",
        "capabilities": ["nearby_food", "nearby_rest_area"],
        "source_type": "restaurant",
    },
    "lodging": {
        "description": "Lodging area and locker hints.",
        "capabilities": ["lodging_area", "locker"],
        "source_type": "lodging",
    },
    "search_mcp": {
        "description": "MCP public web / tourism board / seasonality search.",
        "capabilities": ["public_web_search", "seasonality", "best_time_to_visit"],
        "source_type": "mcp",
    },
    "browser_mcp": {
        "description": "MCP browser for official and dynamic pages.",
        "capabilities": ["official_page_read", "dynamic_page_read"],
        "source_type": "mcp",
    },
    "official_page_reader_mcp": {
        "description": "MCP official page reader for hard facts.",
        "capabilities": ["official_page_read", "opening_hours", "ticket_price"],
        "source_type": "mcp",
    },
    "official_source_discovery_mcp": {
        "description": "Classify search hits for official source candidacy.",
        "capabilities": ["official_source_candidate", "ticket_price", "opening_hours"],
        "source_type": "local",
    },
    "osm_mcp": {
        "description": "MCP OSM geocode, POI, routes.",
        "capabilities": ["geocode", "place_lookup", "nearby_poi", "entity_resolution"],
        "source_type": "mcp",
    },
    "places_mcp": {
        "description": "MCP places lookup.",
        "capabilities": ["place_lookup", "nearby_poi"],
        "source_type": "mcp",
    },
    "geocode_mcp": {
        "description": "MCP geocoding and region lookup.",
        "capabilities": ["geocode", "country_region_lookup"],
        "source_type": "mcp",
    },
    "openmeteo_mcp": {
        "description": "MCP Open-Meteo weather and climate.",
        "capabilities": ["forecast", "monthly_climate", "current_weather"],
        "source_type": "mcp",
    },
    "weather_mcp": {
        "description": "MCP live weather.",
        "capabilities": ["current_weather", "forecast"],
        "source_type": "mcp",
    },
    "climate_mcp": {
        "description": "MCP monthly climate and seasonality support.",
        "capabilities": ["climate_monthly", "monthly_weather", "seasonality"],
        "source_type": "mcp",
    },
    "wikipedia_mcp": {
        "description": "MCP Wikipedia destination background.",
        "capabilities": ["destination_overview", "entity_description"],
        "source_type": "mcp",
    },
    "wikidata_mcp": {
        "description": "MCP Wikidata entity resolution.",
        "capabilities": ["entity_resolution", "alias_lookup"],
        "source_type": "mcp",
    },
    "sqlite_mcp": {
        "description": "MCP read-only evidence / place cache.",
        "capabilities": ["read_evidence_cache", "read_place_cache"],
        "source_type": "mcp",
    },
    "evidence_store_mcp": {
        "description": "MCP evidence store read cache.",
        "capabilities": ["read_evidence_cache", "query_tool_trace"],
        "source_type": "mcp",
    },
    "baidu_place_search_mcp": {
        "description": "百度地图地点检索和 POI 搜索，用于地点解析、消歧、城市/行政区补全",
        "capabilities": [
            "entity_resolution",
            "place_lookup",
            "poi_search",
            "country_region_lookup",
            "city_region_lookup",
        ],
        "source_type": "mcp",
    },
    "baidu_place_detail_mcp": {
        "description": "百度地图地点详情，用于地址、营业时间候选、评分、可能的价格字段",
        "capabilities": [
            "place_details",
            "address_lookup",
            "opening_hours_candidate",
            "price_candidate",
            "rating_candidate",
        ],
        "source_type": "mcp",
    },
    "baidu_weather_mcp": {
        "description": "百度地图天气，用于实时天气和短期预报",
        "capabilities": ["current_weather", "forecast", "weather_risk", "short_term_weather"],
        "source_type": "mcp",
    },
    "baidu_geocode_mcp": {
        "description": "百度地图地理编码，将地址/地名解析为坐标",
        "capabilities": ["geocode", "address_to_coordinates", "city_region_lookup"],
        "source_type": "mcp",
    },
    "baidu_reverse_geocode_mcp": {
        "description": "百度地图逆地理编码，将坐标解析为地址/行政区",
        "capabilities": ["reverse_geocode", "coordinates_to_address", "nearby_context"],
        "source_type": "mcp",
    },
    "baidu_route_mcp": {
        "description": "百度地图路线规划（驾车/步行/公交/骑行）",
        "capabilities": ["route_planning", "transport_planning", "distance", "duration", "route_steps"],
        "source_type": "mcp",
    },
    "baidu_route_matrix_mcp": {
        "description": "百度地图批量距离/时间矩阵，用于多点行程可行性",
        "capabilities": ["directions_matrix", "travel_time_matrix", "itinerary_feasibility"],
        "source_type": "mcp",
    },
    "baidu_traffic_mcp": {
        "description": "百度地图路况查询，用于自驾拥堵与路况风险",
        "capabilities": ["road_traffic", "traffic_status", "congestion_risk", "self_drive_risk"],
        "source_type": "mcp",
    },
    "baidu_ip_location_mcp": {
        "description": "百度地图 IP 定位，仅用于用户授权或明确「我附近」场景",
        "capabilities": ["ip_location", "user_city_estimation", "user_location"],
        "source_type": "mcp",
        "restrictions": ["Requires location_usage_allowed or explicit nearby-me query."],
    },
    "seasonality": {
        "description": "Seasonal / best-time advisory (non-hard-fact).",
        "capabilities": ["seasonality", "best_time_to_visit"],
        "source_type": "seasonality",
    },
    "knowledge_prior": {
        "description": "Low-confidence model prior — only for allowed advisory needs.",
        "capabilities": ["best_time_to_visit", "seasonality"],
        "source_type": "model_prior",
        "restrictions": ["Never for opening hours, ticket price, live weather, or crowd."],
    },
    "fallback": {
        "description": "Low-confidence fallback lookup when primary tools miss.",
        "capabilities": ["fallback_web_lookup", "crowd_level"],
        "source_type": "fallback",
    },
}

_NEED_GATED_TOOLS: dict[str, frozenset[str]] = {
    "restaurant": frozenset({"nearby_food", "nearby_rest_area"}),
    "lodging": frozenset({"lodging_area", "locker"}),
}

_NEARBY_ME_PATTERNS = re.compile(r"我附近|从我这里|附近有什么|离我最近|在我这边|周边", re.I)

_TICKET_PLATFORM_TOOLS = frozenset(
    {
        "fliggy_ticket_crawler_mcp",
        "meituan_ticket_crawler_mcp",
        "dianping_ticket_crawler_mcp",
        "qunar_ticket_crawler_mcp",
    }
)
_REVIEW_PLATFORM_TOOLS = frozenset(
    {
        "review_signal_mcp",
        "public_review_search_mcp",
        "meituan_review_crawler_mcp",
        "qunar_review_crawler_mcp",
        "tripadvisor_review_crawler_mcp",
    }
)
_TRAVEL_NOTE_TOOLS = frozenset(
    {
        "mafengwo_note_crawler_mcp",
        "xiaohongshu_note_crawler_mcp",
        "tourism_board_notice_mcp",
        "platform_notice_crawler_mcp",
    }
)
_NEARBY_PLATFORM_TOOLS = frozenset(
    {
        "nearby_food_mcp",
        "nearby_rest_area_mcp",
        "nearby_toilet_mcp",
        "nearby_parking_mcp",
        "nearby_station_mcp",
        "nearby_attraction_mcp",
        "nearby_hotel_mcp",
        "meituan_nearby_crawler_mcp",
    }
)
_ITINERARY_PLANNER_TOOLS = frozenset(
    {
        "itinerary_planner_mcp",
        "route_feasibility_checker_mcp",
        "elderly_friendly_route_scorer_mcp",
        "family_trip_planner_mcp",
    }
)
_CROWD_ESTIMATION_TOOLS = frozenset(
    {
        "crowd_estimation_mcp",
        "event_calendar_mcp",
    }
)

for _ph in sorted(placeholder_tool_names()):
    _TOOL_CATALOG.setdefault(
        _ph,
        {
            "description": f"S5 placeholder provider tool ({_ph}) — not implemented.",
            "capabilities": ["placeholder_provider"],
            "source_type": "placeholder",
            "implemented": False,
        },
    )

for _tp in sorted(TICKET_PROVIDER_TOOL_NAMES):
    _TOOL_CATALOG.setdefault(
        _tp,
        {
            "description": f"Ticket/review provider ({_tp}).",
            "capabilities": ["ticket_price", "review_summary", "booking_channel"],
            "source_type": "ticket_platform",
        },
    )


def location_usage_allowed(state: TravelAgentState, prompt_context: dict | None = None) -> bool:
    ctx = prompt_context or {}
    user_ctx = ctx.get("user_ctx")
    if user_ctx is not None:
        if isinstance(user_ctx, dict) and user_ctx.get("location_usage_allowed"):
            return True
        if getattr(user_ctx, "location_usage_allowed", False):
            return True
    query = state.raw_user_query or ""
    frame = state.semantic_frame
    if frame:
        query = f"{query} {frame.raw_query} {frame.normalized_request}"
    return bool(_NEARBY_ME_PATTERNS.search(query))


class ToolWhitelistBuilder:
    """Build task-level dynamic tool whitelist for S5 evidence planning."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        tools_registry=None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.tools_registry = tools_registry

    def build(self, state: TravelAgentState, prompt_context: dict | None = None) -> ToolWhitelist:
        if prompt_context and prompt_context.get("gap_filling") and prompt_context.get("gap_request"):
            return self.build_gap_whitelist(prompt_context["gap_request"])
        if state.response_contract:
            return self._build_from_contract(state, prompt_context)
        return self._build_legacy(state, prompt_context)

    def build_gap_whitelist(self, gap) -> ToolWhitelist:
        from app.schemas.evidence_gap_request import EvidenceGapRequest
        from app.orchestrator.ticket_lookup_helpers import TICKET_GAP_FILL_TOOLS

        if isinstance(gap, dict):
            gap = EvidenceGapRequest.model_validate(gap)
        forbidden = set(gap.forbidden_tools or [])
        forbidden.add("knowledge_prior")
        failed = set(gap.failed_tools or [])
        tried = {resolve_tool_name(t) for t in (gap.already_tried_tools or [])}

        if gap.claim_type == "ticket_price":
            pool = [resolve_tool_name(t) for t in TICKET_GAP_FILL_TOOLS]
        else:
            pool = [
                resolve_tool_name(t)
                for t in gap.suggested_tools
                if resolve_tool_name(t) not in forbidden
            ]

        allowed: list[ToolDescriptor] = []
        blocked: dict[str, str] = {}
        for name in pool:
            if name in forbidden or name in failed or name in tried:
                continue
            if name not in EVIDENCE_PLANNING_TOOL_NAMES:
                continue
            ok, reason = self._is_configured(name)
            if ok:
                allowed.append(
                    ToolDescriptor(name=name, description=f"gap-fill for {gap.claim_type}", configured=True)
                )
            else:
                blocked[name] = reason or "not_configured"

        if not allowed and "search_mcp" not in blocked:
            ok, reason = self._is_configured("search_mcp")
            if ok:
                allowed.append(
                    ToolDescriptor(name="search_mcp", description=f"gap-fill for {gap.claim_type}", configured=True)
                )
            else:
                blocked["search_mcp"] = reason or "not_configured"

        notes = [f"S5 gap-filling whitelist for {gap.claim_type}"]
        if blocked:
            notes.append(
                "blocked_tools: "
                + "; ".join(f"{k}: {v}" for k, v in sorted(blocked.items())[:12])
            )
        return ToolWhitelist(
            state_name="evidence_planning_and_tool_use",
            allowed_tools=allowed,
            blocked_tools=sorted(blocked.keys()),
            reason_by_tool=blocked,
            policy_notes=notes,
        )

    def _build_from_contract(self, state: TravelAgentState, prompt_context: dict | None = None) -> ToolWhitelist:
        contract = state.response_contract
        assert contract is not None

        plan = S5DomainPlanner().plan(
            contract,
            state.semantic_frame,
            evidence=state.evidence,
            intent_profile=state.intent_profile,
            intent_strategy=state.intent_strategy,
        )
        state.s5_domain_plan = plan

        domain_candidates = plan.candidate_tool_names()
        forbidden: set[str] = set(plan.effective_forbidden_tool_names())
        candidates: set[str] = set(domain_candidates)
        claim_types: list[str] = []
        contract_preferred: set[str] = set()

        for claim in contract.claim_requirements:
            claim_types.append(claim.claim_type)
            contract_preferred.update(claim.preferred_tools)
            for tool in claim.forbidden_tools:
                if tool == "knowledge_prior":
                    continue
                forbidden.add(tool)

        contract_preferred.update(contract.entity_policy.preferred_tools)
        contract_preferred.update(contract.tool_strategy.initial_tools)
        if state.intent_strategy:
            contract_preferred.update(state.intent_strategy.preferred_tools)
            for tool in state.intent_strategy.forbidden_tools:
                forbidden.add(tool)
            for tool in state.intent_strategy.tool_tiers.forbidden:
                forbidden.add(tool)
        candidates |= contract_preferred
        candidates -= forbidden
        candidates &= set(EVIDENCE_PLANNING_TOOL_NAMES)

        settings = get_settings()
        elevation_only = _contract_is_geo_fact_elevation(contract)
        has_ticket = any(c.claim_type == "ticket_price" for c in contract.claim_requirements)
        if has_ticket:
            from app.orchestrator.ticket_lookup_helpers import TICKET_BOOKING_PRIMARY_TOOLS

            candidates |= set(TICKET_BOOKING_PRIMARY_TOOLS)
        if not elevation_only:
            for tool_name in TICKET_PROVIDER_TOOL_NAMES:
                if provider_configured_for_tool(tool_name, settings):
                    candidates.add(tool_name)
        else:
            for tool in (
                "dianping_ticket_signal_crawler_mcp",
                "dianping_review_crawler_mcp",
                "ctrip_ticket_signal_crawler_mcp",
                "ctrip_review_crawler_mcp",
                "ticket_price_history_query",
                "ticket_snapshot_store",
                "fliggy_ticket_api_mcp",
                "fliggy_ticket_snapshot_crawler_mcp",
                "ticketlens_experience_mcp",
            ):
                forbidden.add(tool)
            candidates &= _GEO_FACT_ELEVATION_ALLOWLIST | candidates

        allow_prior = any(c.model_prior_allowed for c in contract.claim_requirements)
        blocked: dict[str, str] = {}
        policy_notes = [
            "ResponseContract + S5DomainPlan 驱动白名单；claim_types: " + ", ".join(claim_types),
            "S5 domains: " + ", ".join(d.value for d in plan.domains),
        ]
        if forbidden:
            policy_notes.append("forbidden: " + ", ".join(sorted(forbidden)))

        if allow_prior:
            candidates.add("knowledge_prior")
        else:
            blocked["knowledge_prior"] = "forbidden_by_claim_policy: ResponseContract disallows model_prior."
            candidates.discard("knowledge_prior")

        if "baidu_ip_location_mcp" in candidates and not location_usage_allowed(state, prompt_context):
            blocked["baidu_ip_location_mcp"] = "requires_user_permission: IP location needs location_usage_allowed."
            candidates.discard("baidu_ip_location_mcp")

        if state and is_comparison_mode(state):
            for tool in ("wikipedia_mcp", "wikidata_mcp"):
                if tool in candidates:
                    blocked[tool] = "comparison mode: encyclopedia tools deprioritized"
                    candidates.discard(tool)

        return self._finalize_candidates(
            candidates,
            blocked,
            claim_types,
            policy_notes,
            state,
            domain_plan=plan,
            domain_candidates=domain_candidates,
            contract_preferred=contract_preferred,
        )

    def _build_legacy(self, state: TravelAgentState, prompt_context: dict | None = None) -> ToolWhitelist:
        frame = state.semantic_frame
        decision = state.answer_mode_decision
        needs = self._collect_needs(state, frame)
        country = frame.entities.country if frame else None

        candidates: set[str] = set()
        hard_needs = [n for n in needs if n in _HARD_FACT_NEEDS]

        if hard_needs and frame and (frame.requires_exact_fact or frame.requires_live_data):
            for need in hard_needs:
                candidates.update(NEED_TOOL_PROFILES.get(need, []))
            if frame.query_scope == QueryScope.PLACE:
                candidates.update(_PLACE_VALIDATION_TOOLS)
        else:
            for need in needs:
                profile = NEED_TOOL_PROFILES.get(need, [])
                candidates.update(profile)
                for cap_tool, _ in self.capability_registry.tools_for_capability(need, country):
                    policy_name = _CAPABILITY_TO_POLICY.get(cap_tool)
                    if policy_name:
                        candidates.add(policy_name)

        if frame and frame.decision_type == DecisionType.BEST_TIME_TO_VISIT:
            candidates.update(NEED_TOOL_PROFILES.get("best_time_to_visit", []))

        if frame and frame.decision_type == DecisionType.GENERAL_ADVICE:
            candidates.update(NEED_TOOL_PROFILES.get("general_travel_advice", []))

        candidates &= set(EVIDENCE_PLANNING_TOOL_NAMES)

        settings = get_settings()
        for tool_name in TICKET_PROVIDER_TOOL_NAMES:
            if provider_configured_for_tool(tool_name, settings):
                candidates.add(tool_name)

        blocked: dict[str, str] = {}
        policy_notes: list[str] = []

        if any(need in _HARD_FACT_NEEDS for need in needs):
            if "knowledge_prior" in candidates:
                blocked["knowledge_prior"] = "Hard-fact information needs forbid model prior."
                candidates.discard("knowledge_prior")
            policy_notes.append("强事实需求：禁止使用 knowledge_prior。")

        if decision and not decision.allow_knowledge_prior:
            if "knowledge_prior" in candidates:
                blocked["knowledge_prior"] = "AnswerMode does not allow knowledge_prior."
                candidates.discard("knowledge_prior")

        if decision and decision.answer_mode == AnswerMode.EVIDENCE_REQUIRED:
            policy_notes.append("evidence_required：优先 official/places/MCP，不足时记录 limitation。")

        if frame and self._needs_baidu_disambiguation(frame, needs):
            for tool in (
                "baidu_place_search_mcp",
                "baidu_place_detail_mcp",
                "baidu_geocode_mcp",
            ):
                if tool in EVIDENCE_PLANNING_TOOL_NAMES:
                    candidates.add(tool)

        if "baidu_ip_location_mcp" in candidates and not location_usage_allowed(state, prompt_context):
            blocked["baidu_ip_location_mcp"] = (
                "IP location requires location_usage_allowed or explicit nearby-me query."
            )
            candidates.discard("baidu_ip_location_mcp")

        return self._finalize_candidates(candidates, blocked, needs, policy_notes, state)

    def _finalize_candidates(
        self,
        candidates: set[str],
        blocked: dict[str, str],
        needs: list[str],
        policy_notes: list[str],
        state: TravelAgentState | None = None,
        *,
        domain_plan: S5DomainPlan | None = None,
        domain_candidates: set[str] | None = None,
        contract_preferred: set[str] | None = None,
    ) -> ToolWhitelist:
        domain_candidates = domain_candidates or set()
        contract_preferred = contract_preferred or set()
        relevant = domain_candidates | contract_preferred | candidates

        for tool_name in list(candidates):
            if tool_name in _NEED_GATED_TOOLS:
                if not _NEED_GATED_TOOLS[tool_name] & set(needs):
                    blocked[tool_name] = f"No matching information need for {tool_name}."
                    candidates.discard(tool_name)

        allowed: list[ToolDescriptor] = []
        boost_order: list[str] = []
        if state and state.intent_strategy:
            boost_order = list(state.intent_strategy.preferred_tools)

        def _tool_sort_key(name: str) -> tuple[int, str]:
            if name in boost_order:
                return (boost_order.index(name), name)
            return (len(boost_order) + 1, name)

        for tool_name in sorted(candidates, key=_tool_sort_key):
            block_reason = self._block_reason_for_tool(
                tool_name,
                relevant=relevant,
                domain_plan=domain_plan,
            )
            if block_reason:
                blocked[tool_name] = block_reason
                continue

            configured, config_reason = self._is_configured(tool_name)
            meta = _TOOL_CATALOG.get(tool_name, {"description": tool_name, "capabilities": []})
            restrictions = list(meta.get("restrictions", []))
            if tool_name == "knowledge_prior":
                for need in needs:
                    if not EvidencePolicy.model_prior_allowed_for(need):
                        restrictions.append(f"model_prior not allowed for need: {need}")

            from app.orchestrator.agent_tool_catalog import enrich_descriptor_fields, resolve_s5_task_class

            task_class = resolve_s5_task_class(state) if state else None
            enriched = enrich_descriptor_fields(
                tool_name,
                str(meta.get("description", tool_name)),
                task_class=task_class,
            )
            descriptor = ToolDescriptor(
                name=tool_name,
                description=enriched["description"],
                capabilities=list(meta.get("capabilities", [])),
                source_type=meta.get("source_type"),
                requires_api_key=bool(meta.get("requires_api_key", False)),
                configured=configured,
                limitations=[] if configured else [config_reason or "Tool not configured."],
                restrictions=restrictions,
                when_to_use=list(enriched.get("when_to_use") or []),
                when_not_to_use=list(enriched.get("when_not_to_use") or []),
                parameters_hint=str(enriched.get("parameters_hint") or ""),
                prerequisites=list(enriched.get("prerequisites") or []),
                satisfies_needs=list(enriched.get("satisfies_needs") or []),
                call_order_hint=str(enriched.get("call_order_hint") or ""),
            )
            if configured:
                allowed.append(descriptor)
            else:
                blocked[tool_name] = config_reason or "not_configured"

        for tool_name in EVIDENCE_PLANNING_TOOL_NAMES:
            if tool_name in candidates or tool_name in blocked:
                continue
            if domain_plan and tool_name in domain_plan.effective_forbidden_tool_names():
                blocked[tool_name] = "forbidden_by_claim_policy"
                continue
            if is_ticket_provider_tool(tool_name):
                settings = get_settings()
                if not provider_enabled_for_tool(tool_name, settings):
                    blocked[tool_name] = "disabled_by_config"
                elif not provider_configured_for_tool(tool_name, settings):
                    if tool_name in {"ticketlens_experience_mcp", "ticketlens_experience_review_signal_mcp"}:
                        if not settings.ticketlens_api_key:
                            blocked[tool_name] = "missing_api_key"
                        else:
                            blocked[tool_name] = "not_configured"
                    else:
                        blocked[tool_name] = "not_configured"
                elif domain_plan and tool_name not in relevant:
                    blocked[tool_name] = "not_relevant_for_domain"
                else:
                    blocked[tool_name] = "not_relevant_for_domain"
                continue
            if is_crowd_provider_tool(tool_name):
                settings = get_settings()
                if not provider_enabled_for_tool(tool_name, settings):
                    blocked[tool_name] = "disabled_by_config"
                elif not provider_configured_for_tool(tool_name, settings):
                    blocked[tool_name] = "not_configured"
                elif domain_plan and tool_name not in relevant:
                    blocked[tool_name] = "not_relevant_for_domain"
                else:
                    blocked[tool_name] = "not_relevant_for_domain"
                continue
            if is_mcp_policy_placeholder(resolve_tool_name(tool_name)):
                if not self._placeholder_config_enabled(tool_name):
                    blocked[tool_name] = "disabled_by_config"
                else:
                    blocked[tool_name] = "not_implemented"
                continue
            if domain_plan and tool_name in domain_candidates:
                block_reason = self._block_reason_for_tool(tool_name, relevant=relevant, domain_plan=domain_plan)
                if block_reason:
                    blocked[tool_name] = block_reason
                else:
                    blocked[tool_name] = "not_configured"
                continue
            if domain_plan and tool_name not in relevant:
                blocked[tool_name] = "not_relevant_for_domain"
                continue
            if tool_name not in blocked:
                blocked[tool_name] = "Not relevant for current information needs."

        if not allowed:
            policy_notes.append("当前任务无可用工具；可 FINISH 并记录 limitation 或尝试 fallback。")

        blocked_summary = [
            f"{tool}: {reason}" for tool, reason in sorted(blocked.items()) if tool in blocked
        ]
        if blocked_summary:
            policy_notes.append("blocked_tools: " + "; ".join(blocked_summary[:12]))

        return ToolWhitelist(
            state_name="evidence_planning_and_tool_use",
            allowed_tools=allowed,
            blocked_tools=sorted(blocked.keys()),
            reason_by_tool=blocked,
            policy_notes=policy_notes,
        )

    def _block_reason_for_tool(
        self,
        tool_name: str,
        *,
        relevant: set[str],
        domain_plan: S5DomainPlan | None,
    ) -> str | None:
        if domain_plan and tool_name in domain_plan.effective_forbidden_tool_names():
            return "forbidden_by_claim_policy"
        if is_mcp_policy_placeholder(resolve_tool_name(tool_name)):
            if not self._placeholder_config_enabled(tool_name):
                return "disabled_by_config"
            return "not_implemented"
        resolved = resolve_tool_name(tool_name)
        if is_ticket_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                return "disabled_by_config"
            if not provider_configured_for_tool(resolved, settings):
                if resolved in {"ticketlens_experience_mcp", "ticketlens_experience_review_signal_mcp"}:
                    if not settings.ticketlens_api_key:
                        return "missing_api_key"
                if resolved in {"fliggy_ticket_api_mcp", "fliggy_ticket_snapshot_crawler_mcp"}:
                    reason = fliggy_api_block_reason(settings)
                    return reason or "not_configured"
                return "not_configured"
        if is_crowd_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                return "disabled_by_config"
            if not provider_configured_for_tool(resolved, settings):
                return "not_configured"
        if tool_name == "baidu_ip_location_mcp":
            return None
        return None

    @staticmethod
    def _placeholder_config_enabled(tool_name: str) -> bool:
        settings = get_settings()
        if tool_name in _TICKET_PLATFORM_TOOLS:
            return settings.enable_ticket_platform_crawlers
        if tool_name in _REVIEW_PLATFORM_TOOLS:
            return settings.enable_review_platform_crawlers
        if tool_name in _TRAVEL_NOTE_TOOLS:
            return settings.enable_travel_note_crawlers
        if tool_name in _NEARBY_PLATFORM_TOOLS:
            return settings.enable_nearby_platform_crawlers
        if tool_name in _ITINERARY_PLANNER_TOOLS:
            return settings.enable_itinerary_planner_tools
        if tool_name in _CROWD_ESTIMATION_TOOLS:
            return settings.enable_crowd_estimation_tools
        return False

    @staticmethod
    def _needs_baidu_disambiguation(frame: SemanticFrame, needs: list[str]) -> bool:
        if (frame.entities.country or "").lower() not in {"china", "中国"}:
            return False
        if not frame.entities.places:
            return False
        if frame.entities.city:
            return False
        return bool(_BAIDU_DISAMBIGUATION_NEEDS & set(needs))

    @staticmethod
    def _collect_needs(state: TravelAgentState, frame: SemanticFrame | None) -> list[str]:
        if frame and frame.information_needs and (frame.requires_exact_fact or frame.requires_live_data):
            return list(dict.fromkeys(frame.information_needs))
        needs: list[str] = []
        if frame:
            needs.extend(frame.information_needs)
        for item in state.information_needs:
            needs.append(item.need_type.value)
        return list(dict.fromkeys(needs))

    def _mcp_block_reason(self, policy_tool_name: str) -> str:
        spec = MCP_POLICY_SPECS.get(policy_tool_name)
        if spec is None:
            alias = policy_tool_name.replace("official_mcp", "official_page_reader_mcp")
            spec = MCP_POLICY_SPECS.get(alias)
        if spec is None:
            return f"Unknown MCP policy tool {policy_tool_name}"
        server_name = spec[0]
        client = get_mcp_client_manager()
        return client.server_block_reason(server_name)

    def _is_configured(self, policy_tool_name: str) -> tuple[bool, str | None]:
        if policy_tool_name == "official_source_discovery_mcp":
            settings = get_settings()
            if not getattr(settings, "official_source_discovery_enabled", True):
                return False, "disabled_by_config"
            if self.tools_registry is not None and getattr(
                self.tools_registry, "official_source_discovery_mcp", None
            ) is None:
                return False, "not_registered"
            return True, None

        resolved = resolve_tool_name(policy_tool_name)
        if is_ticket_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                return False, "disabled_by_config"
            if resolved == "ticketlens_experience_mcp" and not settings.ticketlens_api_key:
                return False, "missing_api_key"
            if provider_configured_for_tool(resolved, settings):
                return True, None
            if resolved in {
                "ctrip_review_crawler_mcp",
                "ctrip_ticket_signal_crawler_mcp",
                "ctrip_guide_crawler_mcp",
                "fliggy_ticket_api_mcp",
                "fliggy_ticket_snapshot_crawler_mcp",
                "dianping_review_crawler_mcp",
                "dianping_ticket_signal_crawler_mcp",
                "dianping_nearby_crawler_mcp",
            }:
                if resolved in {"fliggy_ticket_api_mcp", "fliggy_ticket_snapshot_crawler_mcp"}:
                    return False, fliggy_api_block_reason(settings) or "not_configured"
                return False, "not_configured"
            if resolved in {"ticket_snapshot_store", "ticket_price_history_query"}:
                return False, "not_configured"
            return False, "missing_api_key"

        if is_crowd_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                return False, "disabled_by_config"
            if provider_configured_for_tool(resolved, settings):
                return True, None
            return False, "not_configured"

        if is_mcp_policy_placeholder(resolve_tool_name(policy_tool_name)):
            if not self._placeholder_config_enabled(policy_tool_name):
                return False, "disabled_by_config"
            return False, mcp_policy_stub_reason(policy_tool_name) or "not_implemented"

        if is_mcp_policy_tool(policy_tool_name) and use_java_tool_gateway():
            return True, None

        if policy_tool_name == "official":
            settings = get_settings()
            if not settings.enable_real_official_page:
                return (
                    False,
                    "official is legacy mock/whitelist tool (ENABLE_REAL_OFFICIAL_PAGE=false); "
                    "use search_mcp for live web evidence, not mock PLACE_REGISTRY",
                )

        if is_mcp_policy_tool(policy_tool_name):
            settings = get_settings()
            if not settings.mcp_enabled:
                return False, "MCP_ENABLED=false"

            stub_reason = mcp_policy_stub_reason(policy_tool_name)
            if stub_reason:
                return False, stub_reason

            spec = MCP_POLICY_SPECS.get(policy_tool_name)
            if spec is None:
                alias = policy_tool_name.replace("official_mcp", "official_page_reader_mcp")
                spec = MCP_POLICY_SPECS.get(alias)
            if spec is None:
                return False, f"Unknown MCP policy tool {policy_tool_name}"

            server_name = spec[0]
            client = get_mcp_client_manager()
            if not client.is_server_configured(server_name):
                return False, self._mcp_block_reason(policy_tool_name)

            if self.tools_registry is not None:
                resolved = resolve_tool_name(policy_tool_name)
                if getattr(self.tools_registry, resolved, None) is None:
                    return False, f"MCP adapter {resolved} not registered."

            return True, None

        if self.tools_registry is None:
            return True, None
        resolved = resolve_tool_name(policy_tool_name)
        if getattr(self.tools_registry, resolved, None) is None:
            return False, f"Registry missing tool {resolved}."
        return True, None
