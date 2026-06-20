import time
from typing import Any

from app.schemas.tool_trace import ToolTrace
from app.tools.fallback_tool import MockFallbackTool
from app.tools.lodging_area_tool import MockLodgingAreaTool
from app.tools.official_site_tool import MockOfficialSiteTool
from app.tools.places_tool import MockPlacesTool
from app.tools.restaurant_tool import MockRestaurantTool
from app.tools.review_tool import MockReviewTool
from app.tools.transit_tool import MockTransitTool
from app.tools.weather_tool import MockWeatherTool


class TravelToolRegistry:
    def __init__(self, use_mock: bool = True) -> None:
        if use_mock:
            self.official = MockOfficialSiteTool()
            self.places = MockPlacesTool()
            self.reviews = MockReviewTool()
            self.weather = MockWeatherTool()
            self.transit = MockTransitTool()
            self.restaurant = MockRestaurantTool()
            self.lodging = MockLodgingAreaTool()
            self.fallback = MockFallbackTool()
        self.traces: list[ToolTrace] = []

    async def run_tool(self, tool_name: str, **kwargs: Any) -> list:
        tool = getattr(self, tool_name, None)
        if tool is None:
            self.traces.append(
                ToolTrace(tool_name=tool_name, input=kwargs, status="error", error="tool not found")
            )
            return []
        start = time.perf_counter()
        try:
            result = await tool.run(**kwargs)
            latency = (time.perf_counter() - start) * 1000
            evidence_ids = [ev.evidence_id for ev in result]
            self.traces.append(
                ToolTrace(tool_name=tool_name, input=kwargs, evidence_ids=evidence_ids, latency_ms=latency, status="ok")
            )
            return result
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            self.traces.append(
                ToolTrace(
                    tool_name=tool_name,
                    input=kwargs,
                    latency_ms=latency,
                    status="error",
                    error=str(exc),
                )
            )
            return []


ToolRegistry = TravelToolRegistry
