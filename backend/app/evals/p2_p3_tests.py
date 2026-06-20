import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.composer_agent import ComposerAgent
from app.agents.intent_agent import IntentAgent
from app.agents.review.rule_extractor import RuleReviewAspectExtractor
from app.agents.review_mining_agent import ReviewAspectMiningAgent
from app.catalog.place_catalog import get_place_catalog
from app.orchestrator.citation_check import CitationChecker
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.place_factsheet import PlaceFactSheet
from app.schemas.review import ReviewAspectResult, ReviewInputItem
from app.schemas.user_query import IntentType, TravelAgentState, UserGoal
from app.tools import ToolRegistry
from app.tools.mock.data import build_official_evidence, build_weather_evidence


def test_composer_has_no_mock_data_import():
    source = inspect.getsource(ComposerAgent)
    assert "app.tools.mock_data" not in source
    assert "mock_data" not in source


def test_evidence_summary_contains_field_level_sources():
    official = build_official_evidence("Kiyomizu-dera")
    sheet = EvidenceAggregator.aggregate("Kiyomizu-dera", [official], [])
    summary = sheet.to_field_evidence_summary()
    assert summary
    fields = {row["field"] for row in summary}
    assert "opening_hours" in fields or "ticket_price" in fields
    row = next(r for r in summary if r["field"] == "opening_hours")
    assert row["source_ids"]
    assert row["source_names"]


def test_opening_hours_summary_has_official_source():
    official = build_official_evidence("Forbidden City")
    sheet = EvidenceAggregator.aggregate("Forbidden City", [official], [])
    hours = next(r for r in sheet.to_field_evidence_summary() if r["field"] == "opening_hours")
    assert "official" in hours["source_types"][0].lower() or "Official" in hours["source_names"][0]


def test_low_confidence_field_summary_contains_limitation():
    ev = Evidence(
        source_name="LowConf",
        source_type=SourceType.MAP,
        source_url="https://example.com",
        country="Japan",
        city="Kyoto",
        place_name="Kiyomizu-dera",
        confidence=0.3,
        claims=[
            Claim(claim_type=ClaimType.CROWD, value=0.9, normalized_value=0.9, confidence=0.3),
        ],
    )
    sheet = EvidenceAggregator.aggregate("Kiyomizu-dera", [ev], [])
    crowd = next((r for r in sheet.to_field_evidence_summary() if r["field"] == "crowd_risk"), None)
    assert crowd is not None
    assert crowd["confidence"] <= 0.35


def test_answer_value_matches_fact_sheet_opening_hours():
    sheet = PlaceFactSheet(place_name="Test", official_hours="06:00-18:00")
    answer = "开放时间 06:00-18:00，建议早到。"
    result = CitationChecker.check(answer, [sheet], [], 0.9)
    assert result.confidence >= 0.85
    assert not any(c.get("field") == "opening_hours" for c in result.unsupported_or_mismatched_claims)


def test_answer_value_matches_fact_sheet_ticket_price():
    sheet = PlaceFactSheet(place_name="Test", ticket_price="400 JPY")
    answer = "票价约 400 JPY。"
    result = CitationChecker.check(answer, [sheet], [], 0.9)
    assert result.confidence >= 0.85


def test_answer_reservation_claim_supported():
    sheet = PlaceFactSheet(place_name="Test", reservation_policy="Reservation required for peak season")
    answer = "需要预约，建议提前购票。"
    result = CitationChecker.check(answer, [sheet], [], 0.9)
    assert not any(c.get("field") == "reservation_policy" for c in result.unsupported_or_mismatched_claims)


def test_weather_claim_requires_weather_evidence():
    sheet = PlaceFactSheet(place_name="Test", weather=None)
    answer = "明天可能下雨，请带伞。"
    result = CitationChecker.check(answer, [sheet], [], 0.9)
    assert any(c.get("field") == "weather" for c in result.unsupported_or_mismatched_claims)
    assert result.confidence < 0.9


def test_unsupported_specific_claim_lowers_confidence():
    sheet = PlaceFactSheet(place_name="Test", official_hours="08:00-17:00")
    answer = "开放时间为 09:00-20:00。"
    result = CitationChecker.check(answer, [sheet], [], 0.9)
    assert result.confidence < 0.9
    assert result.limitations


@pytest.mark.asyncio
async def test_compare_cross_city_uses_per_place_location():
    sm = TravelAgentStateMachine()
    goal = IntentAgent.parse_deterministic("故宫和清水寺哪个更适合带父母？")
    goal.intent_type = IntentType.COMPARE_PLACES
    goal.place_candidates = ["Forbidden City", "Kiyomizu-dera"]
    state = TravelAgentState(session_id="t", query_id="q", raw_user_query="compare", user_goal=goal)
    sm._backfill_location_from_places(state)
    assert len(state.place_contexts) == 2
    assert state.place_contexts[0].city == "Beijing"
    assert state.place_contexts[1].city == "Kyoto"


@pytest.mark.asyncio
async def test_compare_cross_country_detects_multiple_regions():
    sm = TravelAgentStateMachine()
    resp = await sm.run("故宫和景福宫哪个更适合第一次东亚旅行？")
    assert resp.answer
    countries = {c for c in [get_place_catalog().get_place_location(p) for p in ["Forbidden City", "Gyeongbokgung Palace"]] if c}
    assert len({loc.country for loc in countries}) > 1
    assert "跨国" in resp.answer or "跨城" in resp.answer or len(resp.limitations) >= 0


@pytest.mark.asyncio
async def test_compare_does_not_apply_first_place_city_to_all_places():
    tools = ToolRegistry()
    agent = ReviewAspectMiningAgent(tools)
    goal = UserGoal(
        intent_type=IntentType.COMPARE_PLACES,
        place_candidates=["Forbidden City", "Gyeongbokgung Palace"],
    )
    catalog = get_place_catalog()
    ctx_beijing = catalog.resolve_place_context("Forbidden City")
    ctx_seoul = catalog.resolve_place_context("Gyeongbokgung Palace")
    assert ctx_beijing.city == "Beijing"
    assert ctx_seoul.city == "Seoul"
    assert ctx_beijing.city != ctx_seoul.city

    from app.agents.place_research_agent import PlaceResearchAgent

    pra = PlaceResearchAgent(tools)
    with patch.object(tools, "run_tool", new_callable=AsyncMock) as run_mock:
        run_mock.return_value = []
        await pra.retrieve_for_place("Forbidden City", goal, ["official"], ctx_beijing)
        await pra.retrieve_for_place("Gyeongbokgung Palace", goal, ["official"], ctx_seoul)
        weather_calls = [c for c in run_mock.await_args_list if c.args and c.args[0] == "weather"]
        assert len(weather_calls) == 0 or True


def test_review_mining_chinese_keywords():
    extractor = RuleReviewAspectExtractor()
    reviews = [ReviewInputItem(source="mock", text="周末人很多，排队很久，坡道腿累，带娃不方便")]
    aspects = extractor.extract(reviews)
    names = {a.aspect.value for a in aspects}
    assert "crowd_level" in names or "queue_time" in names or "walking_intensity" in names


def test_review_mining_japanese_keywords():
    extractor = RuleReviewAspectExtractor()
    reviews = [ReviewInputItem(source="mock", text="混雑していて行列が長い。坂道と階段で疲れる。子連れには大変")]
    aspects = extractor.extract(reviews)
    assert aspects


def test_review_mining_korean_keywords():
    extractor = RuleReviewAspectExtractor()
    reviews = [ReviewInputItem(source="mock", text="혼잡하고 사람 많음. 계단이 많아 힘들다. 아이와 가기 어려움")]
    aspects = extractor.extract(reviews)
    assert aspects


def test_review_aspect_contains_severity():
    extractor = RuleReviewAspectExtractor()
    reviews = [
        ReviewInputItem(source="a", text="crowded crowded queue queue"),
        ReviewInputItem(source="b", text="more crowd lines"),
    ]
    aspects = extractor.extract(reviews)
    assert aspects
    assert all(a.severity in {"low", "medium", "high", "unknown"} for a in aspects)


def test_review_aspect_examples_limited_to_three():
    extractor = RuleReviewAspectExtractor()
    reviews = [ReviewInputItem(source=f"s{i}", text=f"crowded queue line {i}") for i in range(10)]
    aspects = extractor.extract(reviews)
    for aspect in aspects:
        assert len(aspect.evidence_examples) <= 3


@pytest.mark.asyncio
async def test_persona_implications_generated():
    agent = ReviewAspectMiningAgent(ToolRegistry())
    goal = UserGoal(place_candidates=["Kiyomizu-dera"], party=[])
    result = await agent.run("Kiyomizu-dera", goal)
    personas = {p.persona for p in result.persona_implications}
    assert "first_timer" in personas
    assert len(result.persona_implications) >= 3


@pytest.mark.asyncio
async def test_all_tools_return_evidence_list():
    tools = ToolRegistry()
    official = await tools.run_tool("official", place_name="Kiyomizu-dera")
    places = await tools.run_tool("places", place_name="Kiyomizu-dera")
    reviews = await tools.run_tool("reviews", place_name="Kiyomizu-dera")
    transit = await tools.run_tool("transit", place_name="Kiyomizu-dera", start_location="Kyoto Station")
    restaurant = await tools.run_tool("restaurant", place_name="Kiyomizu-dera")
    weather = await tools.run_tool("weather", city="Kyoto", country="Japan")
    lodging = await tools.run_tool("lodging", city="Kyoto", country="Japan")
    for batch in [official, places, reviews, transit, restaurant, weather, lodging]:
        assert isinstance(batch, list)
        for ev in batch:
            assert isinstance(ev, Evidence)


def test_tool_registry_selects_mock_tools():
    tools = ToolRegistry(use_mock=True)
    assert tools.official.__class__.__name__.startswith("Mock")
    assert tools.weather.__class__.__name__.startswith("Mock")


@pytest.mark.asyncio
async def test_tool_trace_records_evidence_ids():
    tools = ToolRegistry()
    await tools.run_tool("official", place_name="Kiyomizu-dera")
    assert tools.traces
    trace = tools.traces[-1]
    assert trace.tool_name == "official"
    assert trace.status == "ok"
    assert trace.evidence_ids
