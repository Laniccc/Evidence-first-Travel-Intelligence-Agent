import logging
import time
from typing import Any

from app.config import get_settings
from app.schemas.tool_trace import ToolTrace
from app.tools.adapters.mcp_tool_adapter import OfficialReaderMCPAdapter, PlacesMCPAdapter, WeatherMCPAdapter
from app.tools.fallback_tool import MockFallbackTool
from app.tools.hybrid_tool import HybridTravelTool
from app.tools.lodging_area_tool import MockLodgingAreaTool
from app.tools.official_site_tool import MockOfficialSiteTool
from app.tools.places_tool import MockPlacesTool
from app.tools.real.official_page_tool import RealOfficialPageTool
from app.tools.real.places_tool import RealPlacesTool
from app.tools.real.weather_tool import RealWeatherTool
from app.tools.restaurant_tool import MockRestaurantTool
from app.tools.review_tool import MockReviewTool
from app.tools.transit_tool import MockTransitTool
from app.tools.weather_tool import MockWeatherTool

logger = logging.getLogger(__name__)


def _resolve_tool_mode(use_mock: bool | None) -> str:
    if use_mock is True:
        return "mock"
    return get_settings().tool_mode


class TravelToolRegistry:
    def __init__(self, use_mock: bool | None = None) -> None:
        tool_mode = _resolve_tool_mode(use_mock)
        settings = get_settings()

        mock_official = MockOfficialSiteTool()
        mock_places = MockPlacesTool()
        mock_weather = MockWeatherTool()

        if tool_mode == "mock":
            self.official = mock_official
            self.places = mock_places
            self.weather = mock_weather
        else:
            self.official = HybridTravelTool(
                name="official",
                real_tool=RealOfficialPageTool(),
                mock_tool=mock_official,
                settings=settings,
                real_enabled=settings.enable_real_official_page,
                requires_api_key=False,
            )
            self.places = HybridTravelTool(
                name="places",
                real_tool=RealPlacesTool(),
                mock_tool=mock_places,
                settings=settings,
                real_enabled=settings.enable_real_places,
                requires_api_key=True,
            )
            self.weather = HybridTravelTool(
                name="weather",
                real_tool=RealWeatherTool(),
                mock_tool=mock_weather,
                settings=settings,
                real_enabled=settings.enable_real_weather,
                requires_api_key=True,
            )

        self.reviews = MockReviewTool()
        self.transit = MockTransitTool()
        self.restaurant = MockRestaurantTool()
        self.lodging = MockLodgingAreaTool()
        self.fallback = MockFallbackTool()

        self.mcp_weather = WeatherMCPAdapter()
        self.mcp_places = PlacesMCPAdapter()
        self.mcp_official = OfficialReaderMCPAdapter()

        self.tool_mode = tool_mode
        self.traces: list[ToolTrace] = []

    def clear_traces(self) -> None:
        self.traces.clear()

    def record_error(
        self,
        tool_name: str,
        input: dict,
        error: str,
        latency_ms: float = 0.0,
        fallback_used: bool = False,
        cache_hit: bool = False,
    ) -> None:
        self._append_trace(
            ToolTrace(
                tool_name=tool_name,
                input=input,
                evidence_ids=[],
                latency_ms=latency_ms,
                status="error",
                error=error,
                fallback_used=fallback_used,
                cache_hit=cache_hit,
            )
        )

    def record_skipped_tool(self, tool_name: str, error: str, **kwargs: Any) -> None:
        """Backward-compatible alias for record_error."""
        self.record_error(tool_name, input=dict(kwargs), error=error)

    async def run_tool(self, tool_name: str, **kwargs: Any) -> list:
        tool = getattr(self, tool_name, None)
        if tool is None:
            self.record_error(tool_name, input=dict(kwargs), error="tool not found")
            return []
        start = time.perf_counter()
        try:
            result = await tool.run(**kwargs)
            latency = (time.perf_counter() - start) * 1000
            evidence_ids = [ev.evidence_id for ev in result]
            meta = getattr(tool, "last_run_meta", {}) or {}
            trace_input = dict(kwargs)
            if meta.get("fallback_used"):
                trace_input["fallback_used"] = True
            self._append_trace(
                ToolTrace(
                    tool_name=tool_name,
                    input=trace_input,
                    evidence_ids=evidence_ids,
                    latency_ms=latency,
                    status="ok",
                    fallback_used=bool(meta.get("fallback_used")),
                    cache_hit=bool(meta.get("cache_hit")),
                )
            )
            return result
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            if isinstance(tool, HybridTravelTool) and tool.mock_tool is not None:
                try:
                    result = await tool.mock_tool.run(**kwargs)
                    for ev in result:
                        if "fallback_used=true" not in ev.limitations:
                            ev.limitations.append("fallback_used=true")
                    self._append_trace(
                        ToolTrace(
                            tool_name=tool_name,
                            input={**kwargs, "fallback_used": True},
                            evidence_ids=[ev.evidence_id for ev in result],
                            latency_ms=latency,
                            status="ok",
                            fallback_used=True,
                            error=str(exc),
                        )
                    )
                    return result
                except Exception:
                    pass
            self.record_error(tool_name, input=dict(kwargs), error=str(exc), latency_ms=latency)
            return []

    def _append_trace(self, trace: ToolTrace) -> None:
        self.traces.append(trace)


ToolRegistry = TravelToolRegistry
