from app.schemas.evidence import Evidence
from tools.base import BaseTool
from tools.mock_data import build_transit_evidence, normalize_place_name


class MockTransitTool(BaseTool):
    name = "mock_transit"

    async def run(self, place_name: str, start_location: str | None = None, **kwargs) -> list[Evidence]:
        canonical = normalize_place_name(place_name) or place_name
        ev = build_transit_evidence(canonical)
        if ev and start_location:
            ev.limitations.append(f"Route estimate from {start_location} is approximate in mock mode.")
        return [ev] if ev else []
