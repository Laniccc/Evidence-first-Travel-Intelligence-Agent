import pytest

from app.agents.suitability_scorer import TravelSuitabilityScorer
from app.schemas.user_query import PartyType, PaceType, UserGoal


@pytest.mark.asyncio
async def test_persona_weighting_changes_score():
    from app.agents.review_mining_agent import ReviewAspectMiningAgent
    from app.tools import ToolRegistry

    agent = ReviewAspectMiningAgent(ToolRegistry())
    review = await agent.run("Kiyomizu-dera", UserGoal(party=[PartyType.ELDERLY], pace=PaceType.RELAXED))
    rec = TravelSuitabilityScorer.score_place("Kiyomizu-dera", review, UserGoal(party=[PartyType.ELDERLY]))
    assert rec.overall_recommendation in {"recommended", "conditional", "highly_recommended", "not_recommended"}
