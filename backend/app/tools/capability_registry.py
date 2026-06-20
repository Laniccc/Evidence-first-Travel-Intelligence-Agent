from app.tools.capabilities import CostLevel, FreshnessLevel, LatencyLevel, ToolCapability


def build_default_capabilities() -> dict[str, ToolCapability]:
    return {
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
    }


class CapabilityRegistry:
    def __init__(self) -> None:
        self._tools = build_default_capabilities()

    def get(self, tool_name: str) -> ToolCapability | None:
        return self._tools.get(tool_name)

    def tool_has_capability(self, tool_name: str, capability: str) -> bool:
        cap = self._tools.get(tool_name)
        if not cap:
            return False
        return capability in cap.capabilities

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
        return matches

    def all_tool_names(self) -> list[str]:
        return list(self._tools.keys())
