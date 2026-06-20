from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.tools.base import BaseTool
from app.tools.mock_data import PLACE_REGISTRY, normalize_place_name


class MockLodgingAreaTool(BaseTool):
    name = "mock_lodging_area"

    async def run(self, city: str, country: str, **kwargs) -> list[Evidence]:
        return [
            Evidence(
                source_name="Lodging Platform (Mock)",
                source_type=SourceType.LODGING_PLATFORM,
                source_url="https://mock-lodging.local/",
                country=country,
                city=city,
                confidence=0.65,
                claims=[
                    Claim(
                        claim_type=ClaimType.LODGING,
                        value=f"Central {city} districts with good transit access are typical stay areas.",
                        normalized_value={"area": f"Central {city}"},
                        confidence=0.62,
                    )
                ],
                limitations=["Area-level lodging guidance only."],
            )
        ]
