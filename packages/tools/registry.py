import logging
import time
from typing import Any

from app.config import Settings, get_settings
from app.schemas.tool_trace import ToolTrace
from tools.fallback_tool import MockFallbackTool
from tools.hybrid_tool import HybridTravelTool
from tools.knowledge_prior_tool import KnowledgePriorTool
from tools.lodging_area_tool import MockLodgingAreaTool
from tools.mcp.registry_setup import attach_mcp_tools
from tools.ticketing.registry_setup import attach_ticket_providers
from tools.official_site_tool import MockOfficialSiteTool
from tools.places_tool import MockPlacesTool
from tools.real.official_page_tool import RealOfficialPageTool
from tools.real.places_tool import RealPlacesTool
from tools.real.weather_tool import RealWeatherTool
from tools.restaurant_tool import MockRestaurantTool
from tools.review_tool import MockReviewTool
from tools.transit_tool import MockTransitTool
from tools.seasonality_tool import SeasonalityTool
from tools.weather_tool import MockWeatherTool

logger = logging.getLogger(__name__)

BASE_REGISTERED_TOOL_NAMES = (
    "knowledge_prior",
    "official",
    "places",
    "weather",
    "reviews",
    "transit",
    "restaurant",
    "lodging",
    "fallback",
    "seasonality",
)

_REGISTERED_TOOL_NAMES = BASE_REGISTERED_TOOL_NAMES


class TravelToolRegistry:
  """TOOL_MODE-aware registry: mock | hybrid (real→mock) | real (no mock fallback)."""

  def __init__(
      self,
      llm_client=None,
      tool_mode: str | None = None,
      use_mock: bool | None = None,
  ) -> None:
      self.llm = llm_client
      from app.config import get_settings as load_settings

      self.settings = load_settings()
      if use_mock is True:
          raise ValueError("TOOL_MODE=mock is not supported; use real or hybrid with MCP tools.")
      self.tool_mode = tool_mode or self.settings.tool_mode
      if self.tool_mode == "mock":
          raise ValueError("TOOL_MODE=mock is not supported; set TOOL_MODE=real or hybrid.")
      self.traces: list[ToolTrace] = []

      self.knowledge_prior = KnowledgePriorTool(llm_client=self.llm)

      if self.tool_mode == "real":
          self._register_real()
      else:
          self._register_hybrid()

      self._register_shared()

  def _register_mock(self) -> None:
      self.official = MockOfficialSiteTool()
      self.places = MockPlacesTool()
      self.weather = MockWeatherTool()

  def _register_hybrid(self) -> None:
      settings = self._settings_for_mode("hybrid")
      self.official, self.places, self.weather = self._build_hybrid_triplet(
          settings, allow_mock_fallback=True
      )

  def _register_real(self) -> None:
      settings = self._settings_for_mode("real")
      self.official, self.places, self.weather = self._build_hybrid_triplet(
          settings, allow_mock_fallback=False
      )

  def _build_hybrid_triplet(
      self,
      settings: Settings,
      *,
      allow_mock_fallback: bool,
  ) -> tuple[HybridTravelTool, HybridTravelTool, HybridTravelTool]:
      mock_official = MockOfficialSiteTool()
      mock_places = MockPlacesTool()
      mock_weather = MockWeatherTool()
      return (
          HybridTravelTool(
              name="official",
              real_tool=RealOfficialPageTool(),
              mock_tool=mock_official,
              settings=settings,
              real_enabled=settings.enable_real_official_page,
              requires_api_key=False,
              allow_mock_fallback=allow_mock_fallback,
          ),
          HybridTravelTool(
              name="places",
              real_tool=RealPlacesTool(),
              mock_tool=mock_places,
              settings=settings,
              real_enabled=settings.enable_real_places,
              requires_api_key=True,
              allow_mock_fallback=allow_mock_fallback,
          ),
          HybridTravelTool(
              name="weather",
              real_tool=RealWeatherTool(),
              mock_tool=mock_weather,
              settings=settings,
              real_enabled=settings.enable_real_weather,
              requires_api_key=True,
              allow_mock_fallback=allow_mock_fallback,
          ),
      )

  def _register_shared(self) -> None:
      self.reviews = MockReviewTool()
      self.transit = MockTransitTool()
      self.restaurant = MockRestaurantTool()
      self.lodging = MockLodgingAreaTool()
      self.fallback = MockFallbackTool()
      self.seasonality = SeasonalityTool(
          weather_tool=self.weather,
          knowledge_prior_tool=self.knowledge_prior,
      )
      self._mcp_tool_names = attach_mcp_tools(self)
      self._ticket_provider_names = attach_ticket_providers(self)

  def _settings_for_mode(self, mode: str) -> Settings:
      return self.settings.model_copy(update={"tool_mode": mode})

  def registered_tool_names(self) -> list[str]:
      return list(BASE_REGISTERED_TOOL_NAMES) + list(getattr(self, "_mcp_tool_names", [])) + list(
          getattr(self, "_ticket_provider_names", [])
      )

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

  def _trace_fields_from_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
      return {
          "provider": meta.get("provider"),
          "configured": meta.get("configured"),
          "crawler_command": meta.get("crawler_command"),
          "crawler_workdir": meta.get("crawler_workdir"),
          "snapshot_saved_count": meta.get("snapshot_saved_count"),
          "output_parse_status": meta.get("output_parse_status"),
          "error": meta.get("error"),
      }

  async def run_tool(self, tool_name: str, **kwargs: Any) -> list:
      tool = getattr(self, tool_name, None)
      if tool is None:
          self.record_error(tool_name, input=dict(kwargs), error="tool not found")
          return []
      start = time.perf_counter()
      try:
          result = await tool.run(**kwargs)
          latency = (time.perf_counter() - start) * 1000
          if not result and isinstance(tool, HybridTravelTool) and not tool.allow_mock_fallback:
              self.record_error(
                  tool_name,
                  input=dict(kwargs),
                  error=tool.last_run_meta.get("real_error")
                  or "real tool returned no evidence",
                  latency_ms=latency,
              )
              return []
          evidence_ids = [ev.evidence_id for ev in result]
          meta = getattr(tool, "last_run_meta", {}) or {}
          trace_input = dict(kwargs)
          if meta.get("fallback_used"):
              trace_input["fallback_used"] = True
          trace_updates = self._trace_fields_from_meta(meta)
          if trace_updates.get("error"):
              trace_input.setdefault("provider_error", trace_updates["error"])
          self._append_trace(
              ToolTrace(
                  tool_name=tool_name,
                  input=trace_input,
                  evidence_ids=evidence_ids,
                  latency_ms=latency,
                  status="ok",
                  fallback_used=bool(meta.get("fallback_used")),
                  cache_hit=bool(meta.get("cache_hit")),
                  **{k: v for k, v in trace_updates.items() if v is not None},
              )
          )
          return result
      except Exception as exc:
          latency = (time.perf_counter() - start) * 1000
          if (
              self.tool_mode == "hybrid"
              and isinstance(tool, HybridTravelTool)
              and tool.mock_tool is not None
              and tool.allow_mock_fallback
          ):
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
