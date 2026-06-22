from app.config import get_settings
from app.orchestrator.state_policy import EVIDENCE_PLANNING_TOOL_NAMES
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.semantic_frame import AnswerMode, DecisionType, QueryScope, SemanticFrame
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry
from app.tools.mcp.client_manager import get_mcp_client_manager
from app.tools.mcp.tool_specs import MCP_POLICY_SPECS, MCP_POLICY_TOOL_NAMES, NEED_TOOL_PROFILES
from app.tools.mcp.adapter_status import is_mcp_policy_implemented, mcp_policy_stub_reason
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


class ToolWhitelistBuilder:
    """Build task-level dynamic tool whitelist for S5 evidence planning."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry | None = None,
        tools_registry=None,
    ) -> None:
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.tools_registry = tools_registry

    def build(self, state: TravelAgentState) -> ToolWhitelist:
        if state.response_contract:
            return self._build_from_contract(state)
        return self._build_legacy(state)

    def _build_from_contract(self, state: TravelAgentState) -> ToolWhitelist:
        contract = state.response_contract
        assert contract is not None

        candidates: set[str] = set()
        forbidden: set[str] = set()
        claim_types: list[str] = []

        for claim in contract.claim_requirements:
            claim_types.append(claim.claim_type)
            candidates.update(claim.preferred_tools)
            for tool in claim.forbidden_tools:
                if tool == "knowledge_prior":
                    continue
                forbidden.add(tool)

        candidates.update(contract.entity_policy.preferred_tools)
        candidates.update(contract.tool_strategy.initial_tools)
        candidates &= set(EVIDENCE_PLANNING_TOOL_NAMES)
        candidates -= forbidden

        allow_prior = any(c.model_prior_allowed for c in contract.claim_requirements)
        if allow_prior:
            candidates.add("knowledge_prior")

        blocked: dict[str, str] = {}
        policy_notes = [
            "ResponseContract 驱动白名单；claim_types: " + ", ".join(claim_types),
        ]
        if forbidden:
            policy_notes.append("contract forbidden: " + ", ".join(sorted(forbidden)))

        if not allow_prior:
            blocked["knowledge_prior"] = "ResponseContract: no claim allows model_prior."
            candidates.discard("knowledge_prior")

        allowed = self._finalize_candidates(candidates, blocked, claim_types, policy_notes)
        return allowed

    def _build_legacy(self, state: TravelAgentState) -> ToolWhitelist:
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

        if frame and self._needs_baidu_disambiguation(frame, needs):
            for tool in ("baidu_place_search_mcp", "baidu_place_detail_mcp"):
                if tool in EVIDENCE_PLANNING_TOOL_NAMES:
                    candidates.add(tool)

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

        return self._finalize_candidates(candidates, blocked, needs, policy_notes)

    def _finalize_candidates(
        self,
        candidates: set[str],
        blocked: dict[str, str],
        needs: list[str],
        policy_notes: list[str],
    ) -> ToolWhitelist:
        for tool_name in list(candidates):
            if tool_name in _NEED_GATED_TOOLS:
                if not _NEED_GATED_TOOLS[tool_name] & set(needs):
                    blocked[tool_name] = f"No matching information need for {tool_name}."
                    candidates.discard(tool_name)

        allowed: list[ToolDescriptor] = []
        for tool_name in sorted(candidates):
            configured, config_reason = self._is_configured(tool_name)
            meta = _TOOL_CATALOG.get(tool_name, {"description": tool_name, "capabilities": []})
            restrictions = list(meta.get("restrictions", []))
            if tool_name == "knowledge_prior":
                for need in needs:
                    if not EvidencePolicy.model_prior_allowed_for(need):
                        restrictions.append(f"model_prior not allowed for need: {need}")

            descriptor = ToolDescriptor(
                name=tool_name,
                description=meta["description"],
                capabilities=list(meta.get("capabilities", [])),
                source_type=meta.get("source_type"),
                requires_api_key=bool(meta.get("requires_api_key", False)),
                configured=configured,
                limitations=[] if configured else [config_reason or "Tool not configured."],
                restrictions=restrictions,
            )
            if configured:
                allowed.append(descriptor)
            else:
                blocked[tool_name] = config_reason or "Tool not configured."

        for tool_name in EVIDENCE_PLANNING_TOOL_NAMES:
            if tool_name not in candidates and tool_name not in blocked:
                blocked[tool_name] = "Not relevant for current information needs."

        if not allowed:
            policy_notes.append("当前任务无可用工具；可 FINISH 并记录 limitation 或尝试 fallback。")

        blocked_summary = [
            f"{tool}: {reason}" for tool, reason in sorted(blocked.items()) if tool in blocked
        ]
        if blocked_summary:
            policy_notes.append("blocked_tools: " + "; ".join(blocked_summary[:8]))

        return ToolWhitelist(
            state_name="evidence_planning_and_tool_use",
            allowed_tools=allowed,
            blocked_tools=sorted(blocked.keys()),
            reason_by_tool=blocked,
            policy_notes=policy_notes,
        )

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
