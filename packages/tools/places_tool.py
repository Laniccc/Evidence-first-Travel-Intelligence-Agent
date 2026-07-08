from app.schemas.evidence import Evidence
from app.schemas.place import PlaceInfo
from tools.base import BaseTool
from tools.mock_data import PLACE_REGISTRY, normalize_place_name


class MockPlacesTool(BaseTool):
    name = "mock_places"

    async def run(self, place_name: str, **kwargs) -> list[Evidence]:
        canonical = normalize_place_name(place_name) or place_name
        meta = PLACE_REGISTRY.get(canonical)
        if not meta:
            return []
        from tools.mock_data import build_map_evidence

        ev = build_map_evidence(canonical)
        return [ev] if ev else []

    async def get_place_info(self, place_name: str) -> PlaceInfo | None:
        canonical = normalize_place_name(place_name) or place_name
        meta = PLACE_REGISTRY.get(canonical)
        if not meta:
            return None
        return PlaceInfo(
            name=canonical,
            country=meta["country"],
            city=meta["city"],
            address=meta["address"],
            category=meta["category"],
            description=f"Mock profile for {canonical}",
        )
