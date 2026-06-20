import os

import pytest

from app.schemas.evidence import Evidence, SourceType
from app.tools.hybrid_tool import HybridTravelTool
from app.tools.official_site_tool import MockOfficialSiteTool
from app.tools.real.official_page_tool import RealOfficialPageTool


@pytest.mark.real_api
@pytest.mark.asyncio
async def test_official_page_whitelist_returns_evidence():
    if os.getenv("ENABLE_REAL_OFFICIAL_PAGE", "false").lower() != "true":
        pytest.skip("ENABLE_REAL_OFFICIAL_PAGE not enabled")

    tool = RealOfficialPageTool()
    try:
        result = await tool.run(place_name="Kiyomizu-dera", country="Japan", city="Kyoto")
    except Exception as exc:
        pytest.skip(f"Official page fetch unavailable in CI: {exc}")

    assert isinstance(result, list)
    assert result
    ev = result[0]
    assert isinstance(ev, Evidence)
    assert ev.source_type == SourceType.OFFICIAL
    assert ev.retrieved_at is not None
    assert ev.confidence > 0
    assert isinstance(ev.limitations, list)


@pytest.mark.asyncio
async def test_official_hybrid_fallback_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_REAL_OFFICIAL_PAGE", "false")

    hybrid = HybridTravelTool(
        name="official",
        real_tool=RealOfficialPageTool(),
        mock_tool=MockOfficialSiteTool(),
        real_enabled=False,
        requires_api_key=False,
    )
    result = await hybrid.run(place_name="Kiyomizu-dera")
    assert result
    assert hybrid.last_run_meta.get("fallback_used") is True
