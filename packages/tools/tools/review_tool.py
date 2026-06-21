from app.schemas.evidence import Evidence
from tools.base import BaseTool
from tools.mock_data import MOCK_REVIEWS, build_review_evidence, normalize_place_name


class MockReviewTool(BaseTool):
    name = "mock_review"

    async def run(self, place_name: str, **kwargs) -> list[Evidence]:
        canonical = normalize_place_name(place_name) or place_name
        ev = build_review_evidence(canonical)
        return [ev] if ev else []

    def get_raw_reviews(self, place_name: str) -> list[dict]:
        canonical = normalize_place_name(place_name) or place_name
        return MOCK_REVIEWS.get(canonical, [])
