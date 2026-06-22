import os

import pytest

from app.schemas.evidence import Evidence, SourceType
from app.tools.hybrid_tool import HybridTravelTool
from app.tools.places_tool import MockPlacesTool
from app.tools.real.places_tool import RealPlacesTool


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_real_places_returns_evidence_list():
    if not os.getenv("PLACES_API_KEY"):
        pytest.skip("PLACES_API_KEY not set")

    from app.config import get_settings

    if not get_settings().enable_real_places:
        pytest.skip("ENABLE_REAL_PLACES=false")

    tool = RealPlacesTool()
    result = await tool.run(
        place_name="Kiyomizu-dera",
        country="Japan",
        city="Kyoto",
    )
    assert isinstance(result, list)
    assert result
    ev = result[0]
    assert isinstance(ev, Evidence)
    assert ev.source_type == SourceType.MAP
    assert ev.retrieved_at is not None
    assert ev.confidence > 0
    norm = ev.claims[0].normalized_value
    assert "address" in norm
    assert "coordinates" in norm
    assert isinstance(ev.limitations, list)


@pytest.mark.asyncio
async def test_places_hybrid_fallback_without_api_key(monkeypatch):
    monkeypatch.delenv("PLACES_API_KEY", raising=False)
    monkeypatch.setenv("ENABLE_REAL_PLACES", "false")

    hybrid = HybridTravelTool(
        name="places",
        real_tool=RealPlacesTool(),
        mock_tool=MockPlacesTool(),
        real_enabled=False,
        requires_api_key=True,
    )
    result = await hybrid.run(place_name="Kiyomizu-dera", country="Japan", city="Kyoto")
    assert result
    assert hybrid.last_run_meta.get("fallback_used") is True
    assert any("fallback_used=true" in lim for ev in result for lim in ev.limitations)
