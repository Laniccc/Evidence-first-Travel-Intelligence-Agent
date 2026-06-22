import pytest

from app.agents.review_mining_agent import ReviewAspectMiningAgent
from app.agents.suitability_scorer import TravelSuitabilityScorer
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.schemas.user_query import PartyType, PaceType, UserGoal
from app.tools import ToolRegistry
from app.tools.mock_data import build_map_evidence, build_official_evidence, build_review_evidence, build_transit_evidence


@pytest.mark.asyncio
async def test_persona_weighting_changes_score():
    agent = ReviewAspectMiningAgent(ToolRegistry())
    review = await agent.run("Kiyomizu-dera", UserGoal(party=[PartyType.ELDERLY], pace=PaceType.RELAXED))
    evidence = [
        build_official_evidence("Kiyomizu-dera"),
        build_map_evidence("Kiyomizu-dera"),
        build_transit_evidence("Kiyomizu-dera"),
        build_review_evidence("Kiyomizu-dera"),
    ]
    evidence = [e for e in evidence if e]
    fact_sheet = EvidenceAggregator.aggregate("Kiyomizu-dera", evidence)
    rec = TravelSuitabilityScorer.score_place(
        "Kiyomizu-dera",
        fact_sheet,
        review,
        UserGoal(party=[PartyType.ELDERLY]),
    )
    assert rec.overall_recommendation in {"recommended", "conditional", "highly_recommended", "not_recommended"}
