from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from tools.base import BaseTool
from tools.mock_data import PLACE_REGISTRY, normalize_place_name


class MockRestaurantTool(BaseTool):
    name = "mock_restaurant"

    async def run(self, place_name: str, **kwargs) -> list[Evidence]:
        canonical = normalize_place_name(place_name) or place_name
        meta = PLACE_REGISTRY.get(canonical)
        if not meta:
            return []
        area = f"{meta['city']} {meta['category']} district nearby"
        return [
            Evidence(
                source_name="Food Platform (Mock)",
                source_type=SourceType.FOOD_PLATFORM,
                source_url="https://mock-food.local/",
                country=meta["country"],
                city=meta["city"],
                place_name=canonical,
                confidence=0.7,
                claims=[
                    Claim(
                        claim_type=ClaimType.FOOD,
                        value=f"Nearby dining clusters around {area}; specific restaurants not verified.",
                        normalized_value={"area_recommendation": area},
                        confidence=0.68,
                    )
                ],
                limitations=["Area-level recommendation only; no specific restaurant verified."],
            )
        ]
