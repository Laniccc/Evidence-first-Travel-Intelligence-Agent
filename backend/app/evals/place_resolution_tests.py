import pytest
from unittest.mock import AsyncMock, patch

from app.agents.place_entity_extractor import GEO_CITY_ALIASES, LLMPlaceEntityExtractor
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.catalog.place_resolver import MockCatalogResolver, PlaceResolver, build_place_resolvers
from app.config import get_settings
from app.schemas.conversation_context import ConversationContext
from app.schemas.place_candidate import PlaceResolutionSource
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.travel_task import TravelTask, TravelTaskType


@pytest.fixture(autouse=True)
def _clear_place_cache():
    from pathlib import Path

    from app.storage.place_cache import PlaceCache

    path = PlaceCache().path
    if path.exists():
        path.unlink()
    yield
    if path.exists():
        path.unlink()


@pytest.fixture(autouse=True)
def _disable_mock_place_resolution(monkeypatch):
    monkeypatch.setenv("PLACE_RESOLUTION_USE_MOCK", "false")
    get_settings.cache_clear()


def test_place_entity_extractor_sapporo_without_mock_registry(monkeypatch):
    monkeypatch.setitem(GEO_CITY_ALIASES, "札幌", ("Japan", "Sapporo"))
    mentions = LLMPlaceEntityExtractor.extract_sync("札幌适合几月份去？", ConversationContext())
    assert any(m.entity_type == "city" and m.city == "Sapporo" for m in mentions)


def test_default_resolver_chain_excludes_mock_catalog(monkeypatch):
    monkeypatch.setenv("PLACE_RESOLUTION_USE_MOCK", "false")
    get_settings.cache_clear()
    names = [r.name for r in build_place_resolvers()]
    assert "mock_catalog" not in names


def test_mock_catalog_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("PLACE_RESOLUTION_USE_MOCK", "true")
    get_settings.cache_clear()
    names = [r.name for r in build_place_resolvers()]
    assert names[-1] == "mock_catalog"


def test_place_resolver_prefers_geocode_over_mock_catalog(monkeypatch):
    async def never_mock(self, raw_query, mention, context):
        raise AssertionError("MockCatalogResolver should not run when geocode succeeds")

    monkeypatch.setattr(MockCatalogResolver, "resolve", never_mock)
    candidates = PlaceResolver.resolve_sync("札幌适合几月份去？", ConversationContext(), llm_client=None)
    city_hit = next(c for c in candidates if c.is_city)
    assert city_hit.city == "Sapporo"
    assert city_hit.country == "Japan"
    assert city_hit.resolution_source in {
        PlaceResolutionSource.LLM_GEocode,
        PlaceResolutionSource.LOCAL_CACHE,
    }


def test_poi_geocode_without_mock_catalog(monkeypatch):
    candidates = PlaceResolver.resolve_sync("札幌电视塔今天几点关门？", ConversationContext())
    poi = next((c for c in candidates if c.is_poi), None)
    assert poi is not None
    assert poi.country == "Japan"
    assert poi.city == "Sapporo"
    assert poi.resolution_source == PlaceResolutionSource.LLM_GEocode
    assert "塔" in poi.canonical_name


def test_semantic_frame_city_scope_without_place_registry_poi():
    raw = "札幌适合几月份去？"
    task = TravelTask(
        task_type=TravelTaskType.OPEN_ENDED_ADVICE,
        country="Japan",
        city="Sapporo",
        key_concerns=["seasonality"],
    )
    qu = QueryUnderstandingResult(rewritten_query=raw, travel_task=task, confidence=0.85)
    candidates = PlaceResolver.resolve_sync(raw, ConversationContext())
    frame = SemanticFrameBuilder.build(raw, qu, candidates)
    assert frame.query_scope.value == "city"
    assert frame.entities.city == "Sapporo"
    assert frame.entities.country == "Japan"
    assert frame.entities.places == []
    assert frame.decision_type.value == "best_time_to_visit"


def test_poi_identification_does_not_imply_opening_hours_fact():
    raw = "札幌电视塔今天几点关门？"
    candidates = PlaceResolver.resolve_sync(raw, ConversationContext())
    poi = next((c for c in candidates if c.is_poi), None)
    assert poi is not None
    assert "塔" in poi.mention or "电视" in poi.mention
    task = TravelTask(
        task_type=TravelTaskType.PLACE_FACT_LOOKUP,
        country=poi.country or "Japan",
        city=poi.city or "Sapporo",
        key_concerns=["opening_hours"],
    )
    qu = QueryUnderstandingResult(rewritten_query=raw, travel_task=task, confidence=0.8)
    frame = SemanticFrameBuilder.build(raw, qu, candidates)
    assert frame.requires_exact_fact is True
    assert frame.can_answer_with_model_prior is False
    assert "opening_hours" in frame.information_needs


@pytest.mark.asyncio
async def test_sapporo_best_month_end_to_end():
    from app.orchestrator.state_machine import TravelAgentStateMachine
    from app.schemas.normalized_user_request import (
        AnswerPolicyDraft,
        InformationNeedDraft,
        NormalizedEntity,
        NormalizedTimeScope,
        NormalizedUserRequest,
    )

    sapporo = NormalizedUserRequest(
        raw_query="札幌适合几月份去？",
        rewritten_query="札幌适合几月份去？（最佳季节建议）",
        intent_summary="札幌最佳出行月份",
        query_scope="city",
        task_family="advisory",
        decision_type="best_time_to_visit",
        entities=[
            NormalizedEntity(
                text="札幌",
                normalized_name="Sapporo",
                entity_type="city",
                country="Japan",
                city="Sapporo",
                confidence=0.9,
            )
        ],
        time_scope=NormalizedTimeScope(scope="seasonal"),
        information_needs=[InformationNeedDraft(need_type="best_time_to_visit")],
        answer_policy=AnswerPolicyDraft(can_answer_with_model_prior=True),
        confidence=0.9,
    )

    sm = TravelAgentStateMachine()
    with patch.object(
        sm.llm_understanding_state.agent,
        "run",
        new_callable=AsyncMock,
        return_value=sapporo,
    ):
        resp = await sm.run("札幌适合几月份去？")
    assert resp.semantic_frame_summary["query_scope"] == "city"
    assert resp.semantic_frame_summary["entities"]["city"] == "Sapporo"
    assert resp.answer_mode == "model_prior_allowed"
