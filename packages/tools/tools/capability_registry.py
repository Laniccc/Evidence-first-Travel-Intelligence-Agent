from app.config import get_settings
from tools.capabilities import CostLevel, FreshnessLevel, LatencyLevel, ToolCapability


def build_default_capabilities(tool_mode: str | None = None) -> dict[str, ToolCapability]:
    mode = tool_mode or get_settings().tool_mode
    caps: dict[str, ToolCapability] = {
        "official": ToolCapability(
            tool_name="official",
            capabilities=[
                "opening_hours",
                "ticket_price",
                "reservation_policy",
                "temporary_closure",
            ],
            freshness=FreshnessLevel.STATIC,
            confidence_by_capability={
                "opening_hours": 0.95,
                "ticket_price": 0.9,
                "reservation_policy": 0.9,
                "temporary_closure": 0.85,
            },
        ),
        "places": ToolCapability(
            tool_name="places",
            capabilities=[
                "address",
                "opening_status",
                "popular_times_proxy",
                "nearby_poi",
                "accessibility_proxy",
                "crowd_level",
            ],
            freshness=FreshnessLevel.RECENT,
            confidence_by_capability={
                "crowd_level": 0.55,
                "popular_times_proxy": 0.5,
                "accessibility_proxy": 0.6,
            },
        ),
        "reviews": ToolCapability(
            tool_name="reviews",
            capabilities=[
                "crowd_level",
                "queue_time",
                "walking_intensity",
                "accessibility",
                "stroller_friendliness",
                "family_friendliness",
                "overrated_risk",
                "commercialization",
                "weather_sensitivity",
            ],
            freshness=FreshnessLevel.RECENT,
            confidence_by_capability={
                "crowd_level": 0.7,
                "queue_time": 0.65,
                "walking_intensity": 0.75,
                "accessibility": 0.65,
            },
        ),
        "weather": ToolCapability(
            tool_name="weather",
            capabilities=["weather", "weather_risk", "event"],
            freshness=FreshnessLevel.DAILY,
            confidence_by_capability={"weather": 0.8, "event": 0.4},
        ),
        "transit": ToolCapability(
            tool_name="transit",
            capabilities=["transit", "walking_intensity_proxy"],
            freshness=FreshnessLevel.RECENT,
            confidence_by_capability={"transit": 0.85},
        ),
        "restaurant": ToolCapability(
            tool_name="restaurant",
            capabilities=["nearby_food", "nearby_rest_area"],
            freshness=FreshnessLevel.RECENT,
            confidence_by_capability={"nearby_food": 0.7, "nearby_rest_area": 0.55},
        ),
        "lodging": ToolCapability(
            tool_name="lodging",
            capabilities=["lodging_area", "locker"],
            freshness=FreshnessLevel.STATIC,
            confidence_by_capability={"lodging_area": 0.6},
        ),
        "fallback": ToolCapability(
            tool_name="fallback",
            capabilities=[
                "fallback_web_lookup",
                "temporary_closure",
                "event",
                "unregistered_information_need",
                "crowd_level",
                "locker",
                "stroller_friendliness",
                "photo_spot",
            ],
            freshness=FreshnessLevel.UNKNOWN,
            confidence_by_capability={"fallback_web_lookup": 0.35, "crowd_level": 0.4, "event": 0.35},
            cost_level=CostLevel.MEDIUM,
            latency_level=LatencyLevel.MEDIUM,
        ),
        "mock_weather_tool": ToolCapability(
            tool_name="mock_weather_tool",
            capabilities=["weather", "weather_risk", "event"],
            freshness=FreshnessLevel.DAILY,
            confidence_by_capability={"weather": 0.55, "weather_risk": 0.5},
            requires_api_key=False,
        ),
        "mock_places_tool": ToolCapability(
            tool_name="mock_places_tool",
            capabilities=[
                "address",
                "opening_status",
                "popular_times_proxy",
                "nearby_poi",
                "accessibility_proxy",
                "crowd_level",
            ],
            freshness=FreshnessLevel.RECENT,
            confidence_by_capability={"address": 0.55, "crowd_level": 0.45},
            requires_api_key=False,
        ),
        "mock_official_tool": ToolCapability(
            tool_name="mock_official_tool",
            capabilities=[
                "opening_hours",
                "ticket_price",
                "reservation_policy",
                "temporary_closure",
            ],
            freshness=FreshnessLevel.STATIC,
            confidence_by_capability={"opening_hours": 0.6},
            requires_api_key=False,
        ),
    }

    if mode in {"real", "hybrid"}:
        caps["real_weather_tool"] = ToolCapability(
            tool_name="real_weather_tool",
            capabilities=["weather", "weather_risk", "event"],
            freshness=FreshnessLevel.LIVE,
            confidence_by_capability={"weather": 0.85, "weather_risk": 0.8},
            requires_api_key=True,
        )
        caps["real_places_tool"] = ToolCapability(
            tool_name="real_places_tool",
            capabilities=[
                "address",
                "opening_status",
                "popular_times_proxy",
                "nearby_poi",
                "accessibility_proxy",
            ],
            freshness=FreshnessLevel.RECENT,
            confidence_by_capability={"address": 0.75},
            requires_api_key=True,
        )
        caps["real_official_page_tool"] = ToolCapability(
            tool_name="real_official_page_tool",
            capabilities=[
                "opening_hours",
                "ticket_price",
                "reservation_policy",
                "temporary_closure",
            ],
            freshness=FreshnessLevel.STATIC,
            confidence_by_capability={"opening_hours": 0.9},
            requires_api_key=False,
        )
        if get_settings().mcp_enabled:
            caps["search_mcp"] = ToolCapability(
                tool_name="search_mcp",
                capabilities=["public_web_search", "seasonality", "best_time_to_visit", "seasonal_events"],
                freshness=FreshnessLevel.RECENT,
            )
            caps["browser_mcp"] = ToolCapability(
                tool_name="browser_mcp",
                capabilities=["official_page_read", "opening_hours", "temporary_closure"],
                freshness=FreshnessLevel.STATIC,
            )
            caps["official_page_reader_mcp"] = ToolCapability(
                tool_name="official_page_reader_mcp",
                capabilities=["official_page_read", "opening_hours", "ticket_price", "reservation_policy"],
                freshness=FreshnessLevel.STATIC,
            )
            caps["osm_mcp"] = ToolCapability(
                tool_name="osm_mcp",
                capabilities=["geocode", "place_lookup", "nearby_poi", "entity_resolution"],
                freshness=FreshnessLevel.RECENT,
            )
            caps["places_mcp"] = ToolCapability(
                tool_name="places_mcp",
                capabilities=["place_lookup", "nearby_poi", "address"],
                freshness=FreshnessLevel.RECENT,
            )
            caps["geocode_mcp"] = ToolCapability(
                tool_name="geocode_mcp",
                capabilities=["geocode", "country_region_lookup", "entity_resolution"],
                freshness=FreshnessLevel.STATIC,
            )
            caps["openmeteo_mcp"] = ToolCapability(
                tool_name="openmeteo_mcp",
                capabilities=["weather", "forecast", "climate_monthly", "monthly_weather", "seasonality"],
                freshness=FreshnessLevel.LIVE,
            )
            caps["weather_mcp"] = ToolCapability(
                tool_name="weather_mcp",
                capabilities=["weather", "weather_today", "today_weather", "forecast"],
                freshness=FreshnessLevel.LIVE,
            )
            caps["climate_mcp"] = ToolCapability(
                tool_name="climate_mcp",
                capabilities=["climate_monthly", "monthly_weather", "seasonality"],
                freshness=FreshnessLevel.DAILY,
            )
            caps["wikipedia_mcp"] = ToolCapability(
                tool_name="wikipedia_mcp",
                capabilities=["destination_overview", "entity_description", "best_time_to_visit"],
                freshness=FreshnessLevel.STATIC,
            )
            caps["wikidata_mcp"] = ToolCapability(
                tool_name="wikidata_mcp",
                capabilities=["entity_resolution", "alias_lookup"],
                freshness=FreshnessLevel.STATIC,
            )
            caps["sqlite_mcp"] = ToolCapability(
                tool_name="sqlite_mcp",
                capabilities=["read_evidence_cache", "read_place_cache"],
                freshness=FreshnessLevel.RECENT,
            )
            caps["evidence_store_mcp"] = ToolCapability(
                tool_name="evidence_store_mcp",
                capabilities=["read_evidence_cache", "query_tool_trace"],
                freshness=FreshnessLevel.RECENT,
            )

    return caps


_EXECUTION_ALIASES = {
    "real_weather_tool": "weather",
    "mock_weather_tool": "weather",
    "real_places_tool": "places",
    "mock_places_tool": "places",
    "real_official_page_tool": "official",
    "mock_official_tool": "official",
    "official_reader_mcp": "official_page_reader_mcp",
}

_PILOT_REAL_MOCK = {
    "weather": ("real_weather_tool", "mock_weather_tool"),
    "places": ("real_places_tool", "mock_places_tool"),
    "official": ("real_official_page_tool", "mock_official_tool"),
}


class CapabilityRegistry:
    def __init__(self, tool_mode: str | None = None) -> None:
        self.tool_mode = tool_mode or get_settings().tool_mode
        self._tools = build_default_capabilities(self.tool_mode)

    def get(self, tool_name: str) -> ToolCapability | None:
        return self._tools.get(tool_name)

    def tool_has_capability(self, tool_name: str, capability: str) -> bool:
        cap = self._tools.get(tool_name)
        if not cap:
            return False
        return capability in cap.capabilities

    def execution_tool_name(self, logical_tool: str) -> str:
        return _EXECUTION_ALIASES.get(logical_tool, logical_tool)

    def tools_for_capability(self, capability: str, country: str | None = None) -> list[tuple[str, float]]:
        matches: list[tuple[str, float]] = []
        for name, cap in self._tools.items():
            if capability not in cap.capabilities:
                continue
            if country and cap.supported_countries and country not in cap.supported_countries:
                continue
            conf = cap.confidence_by_capability.get(capability, 0.5)
            matches.append((name, conf))
        matches.sort(key=lambda x: x[1], reverse=True)
        return self._prioritize_real_tools(matches, capability)

    def _prioritize_real_tools(
        self, matches: list[tuple[str, float]], capability: str
    ) -> list[tuple[str, float]]:
        if self.tool_mode == "mock":
            return [(n, c) for n, c in matches if not n.startswith("real_") and not n.endswith("_mcp")]

        real_first: list[tuple[str, float]] = []
        others: list[tuple[str, float]] = []
        for name, conf in matches:
            if name.startswith("real_") or name.endswith("_mcp"):
                real_first.append((name, conf))
            else:
                others.append((name, conf))
        if self.tool_mode == "real":
            return real_first or others
        return real_first + others

    def pilot_chain_for_execution_tool(self, execution_tool: str) -> tuple[str | None, list[str]]:
        if execution_tool not in _PILOT_REAL_MOCK:
            return execution_tool, []
        primary, fallback = _PILOT_REAL_MOCK[execution_tool]
        if self.tool_mode == "mock":
            _, fallback = _PILOT_REAL_MOCK[execution_tool]
            return fallback, []
        if self.tool_mode == "real":
            return primary, [fallback]
        return primary, [fallback]

    def all_tool_names(self) -> list[str]:
        return list(self._tools.keys())
