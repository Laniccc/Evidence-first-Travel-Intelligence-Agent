"""LLM structured review extraction — disabled by default in MVP."""

from app.schemas.review import ReviewAspect, ReviewInputItem


class LLMReviewAspectExtractor:
    enabled: bool = False

    async def extract(self, reviews: list[ReviewInputItem]) -> list[ReviewAspect]:
        if not self.enabled:
            return []
        # Future: call LLM and model_validate_json into list[ReviewAspect]
        return []
