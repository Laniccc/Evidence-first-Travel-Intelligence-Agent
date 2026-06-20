import compileall
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.composer_agent import ComposerAgent, ItineraryAgent
from app.agents.intent_agent import IntentAgent
from app.agents.place_research_agent import PlaceResearchAgent
from app.agents.review_mining_agent import VerifierAgent
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.policies import SourceSelectionPolicy
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.user_query import IntentType, UserGoal
from app.tools import ToolRegistry


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_compile_imports():
    ok = compileall.compile_dir(str(BACKEND_ROOT / "app"), quiet=1)
    assert ok, "compileall failed for backend/app"
    import app.main  # noqa: F401
    import app.orchestrator.evidence_aggregator  # noqa: F401
    import app.schemas.place_factsheet  # noqa: F401


@pytest.mark.asyncio
async def test_weather_called_when_city_backfilled():
    goal = IntentAgent.parse_deterministic("京都清水寺适合带父母去吗？")
    sm = TravelAgentStateMachine()
    sm._backfill_location_from_places(goal)
    assert goal.place_candidates
    assert goal.destination_city == "Kyoto"
    assert goal.destination_country == "Japan"

    tools = ToolRegistry()
    agent = PlaceResearchAgent(tools)
    tool_names = SourceSelectionPolicy.select_tools(goal)
    assert "weather" in tool_names

    with patch.object(tools.weather, "run", new_callable=AsyncMock) as weather_mock:
        weather_mock.return_value = []
        await agent.retrieve_for_place(goal.place_candidates[0], goal, tool_names)
        weather_mock.assert_awaited_once()
        kwargs = weather_mock.await_args.kwargs
        assert kwargs["city"] == "Kyoto"
        assert kwargs["country"] == "Japan"


@pytest.mark.asyncio
async def test_no_unbacked_opening_hours():
    sm = TravelAgentStateMachine()
    resp = await sm.run("京都清水寺适合带父母去吗？", {"party": ["elderly"]})
    assert resp.answer
    if "开放时间" in resp.answer or "opening" in resp.answer.lower():
        assert any(
            ClaimType.OPENING_HOURS.value in str(e) or "Official" in e.get("source_name", "")
            for e in resp.evidence_summary
        ) or any("official_hours" in str(resp.structured_result) for _ in [0])


@pytest.mark.asyncio
async def test_no_unbacked_ticket_price():
    sm = TravelAgentStateMachine()
    resp = await sm.run("北京故宫明天值得去吗？")
    places = resp.structured_result.places or []
    if places and isinstance(places[0], dict) and "fact_sheet" in places[0]:
        fs = places[0]["fact_sheet"]
        if "票价" in resp.answer:
            assert fs.get("ticket_price"), "ticket_price should be backed by evidence"
            assert fs.get("source_ids", {}).get("ticket_price")


def test_composer_does_not_depend_on_registry_directly():
    source = inspect.getsource(ComposerAgent)
    assert "PLACE_REGISTRY" not in source
    scorer_source = inspect.getsource(__import__("app.agents.suitability_scorer", fromlist=["TravelSuitabilityScorer"]).TravelSuitabilityScorer)
    assert "PLACE_REGISTRY" not in scorer_source


def test_conflict_resolution_prefers_official():
    official = Evidence(
        source_name="Official",
        source_type=SourceType.OFFICIAL,
        source_url="https://official.example",
        country="China",
        city="Beijing",
        place_name="Forbidden City",
        claims=[
            Claim(claim_type=ClaimType.OPENING_HOURS, value="08:30-17:00", normalized_value="08:30-17:00", confidence=0.95),
            Claim(claim_type=ClaimType.TICKET_PRICE, value="60 CNY", normalized_value="60 CNY", confidence=0.9),
        ],
    )
    map_ev = Evidence(
        source_name="Map",
        source_type=SourceType.MAP,
        source_url="https://maps.example",
        country="China",
        city="Beijing",
        place_name="Forbidden City",
        claims=[
            Claim(claim_type=ClaimType.OPENING_HOURS, value="09:00-16:00", normalized_value="09:00-16:00", confidence=0.8),
            Claim(claim_type=ClaimType.TICKET_PRICE, value="80 CNY", normalized_value="80 CNY", confidence=0.7),
        ],
    )
    evidence = [map_ev, official]
    conflicts = VerifierAgent.detect_conflicts(evidence)
    assert conflicts
    winner_hours = SourceSelectionPolicy.resolve_conflict_winners(evidence, "opening_hours")
    assert winner_hours == "Official"
    sheet = EvidenceAggregator.aggregate("Forbidden City", evidence, conflicts)
    assert sheet.official_hours == "08:30-17:00"
    assert sheet.ticket_price == "60 CNY"


def test_itinerary_uses_registered_places_only():
    goal = UserGoal(
        intent_type=IntentType.ITINERARY,
        destination_country="Japan",
        destination_city="Tokyo",
        start_location="Shinjuku",
    )
    plan = ItineraryAgent.build(goal)
    place_names = [i.place_name for i in plan.items if i.place_name]
    from app.tools.mock_data import PLACE_REGISTRY

    assert place_names, "itinerary should include registered places"
    for name in place_names:
        assert name in PLACE_REGISTRY


def test_source_selection_differs_by_intent():
    single = UserGoal(intent_type=IntentType.SINGLE_PLACE, place_candidates=["Kiyomizu-dera"])
    compare = UserGoal(intent_type=IntentType.COMPARE_PLACES, place_candidates=["Kiyomizu-dera", "Fushimi Inari"])
    itinerary = UserGoal(intent_type=IntentType.ITINERARY, destination_city="Seoul", destination_country="South Korea")
    assert "restaurant" in SourceSelectionPolicy.select_tools(single)
    assert "weather" in SourceSelectionPolicy.select_tools(single)
    assert "restaurant" not in SourceSelectionPolicy.select_tools(compare)
    assert "lodging" in SourceSelectionPolicy.select_tools(itinerary)
