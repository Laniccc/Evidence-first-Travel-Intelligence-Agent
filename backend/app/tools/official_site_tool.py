from app.schemas.evidence import Evidence
from app.tools.base import BaseTool
from app.tools.mock_data import build_official_evidence, normalize_place_name


class MockOfficialSiteTool(BaseTool):
    name = "mock_official_site"

    async def run(self, place_name: str, **kwargs) -> list[Evidence]:
        canonical = normalize_place_name(place_name) or place_name
        ev = build_official_evidence(canonical)
        return [ev] if ev else []
