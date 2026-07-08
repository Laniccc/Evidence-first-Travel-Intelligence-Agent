import os

import pytest

from app.schemas.evidence import Evidence, SourceType
from app.tools.hybrid_tool import HybridTravelTool
from app.tools.real.weather_tool import RealWeatherTool
from app.tools.weather_tool import MockWeatherTool


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_real_weather_returns_evidence_list():
    if not os.getenv("WEATHER_API_KEY"):
        pytest.skip("WEATHER_API_KEY not set")
    tool = RealWeatherTool()
    if not tool.is_available():
        pytest.skip("ENABLE_REAL_WEATHER=false or missing API key")

    result = await tool.run(city="Kyoto", country="Japan", travel_date="2026-06-21")
    assert isinstance(result, list)
    assert result
    assert all(isinstance(ev, Evidence) for ev in result)
    ev = result[0]
    assert ev.source_type == SourceType.WEATHER_API
    assert ev.retrieved_at is not None
    assert ev.confidence > 0
    norm = ev.claims[0].normalized_value
    assert "weather" in norm
    assert "temperature_range" in norm
    assert "precipitation_probability" in norm
    assert "weather_risk" in norm


@pytest.mark.asyncio
async def test_weather_hybrid_fallback_without_api_key(monkeypatch):
    monkeypatch.setenv("TOOL_MODE", "hybrid")
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    monkeypatch.setenv("ENABLE_REAL_WEATHER", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    hybrid = HybridTravelTool(
        name="weather",
        real_tool=RealWeatherTool(),
        mock_tool=MockWeatherTool(),
        real_enabled=False,
        requires_api_key=True,
    )
    result = await hybrid.run(city="Kyoto", country="Japan", travel_date="2026-06-21")
    assert result
    assert hybrid.last_run_meta.get("fallback_used") is True
    assert any("fallback_used=true" in lim for ev in result for lim in ev.limitations)


@pytest.mark.asyncio
async def test_weather_hybrid_api_failure_fallback(monkeypatch):
    class FailingReal(RealWeatherTool):
        async def run(self, **kwargs):
            raise RuntimeError("simulated API failure")

    hybrid = HybridTravelTool(
        name="weather",
        real_tool=FailingReal(),
        mock_tool=MockWeatherTool(),
        real_enabled=True,
        requires_api_key=False,
    )
    monkeypatch.setattr(hybrid, "_should_try_real", lambda: True)
    result = await hybrid.run(city="Kyoto", country="Japan")
    assert result
    assert hybrid.last_run_meta.get("fallback_used") is True
