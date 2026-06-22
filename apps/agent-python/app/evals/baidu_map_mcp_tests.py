"""Baidu Map MCP integration tests."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.schemas.semantic_frame import (
    AnswerMode,
    AnswerModeDecision,
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.user_query import TravelAgentState
from app.tools import ToolRegistry
from app.tools.mcp.client_manager import get_mcp_client_manager, reset_mcp_client_manager


def _baidu_settings(**overrides) -> Settings:
    base = {
        "mcp_enabled": True,
        "mcp_baidu_map_enabled": True,
        "baidu_map_ak": "test-ak",
        "mcp_baidu_map_server_url": "mock://",
        "mcp_baidu_map_transport": "baidu_streamable_http",
        "mcp_profile": "search_only",
    }
    base.update(overrides)
    return Settings(**base)


def _register_baidu_mocks() -> None:
    mgr = get_mcp_client_manager()

    def search_yunfeng(_args):
        return {
            "results": [
                {"name": "云峰山", "uid": "uid-ln", "province": "辽宁", "city": "丹东", "address": "辽宁丹东"},
                {"name": "云峰山", "uid": "uid-hn", "province": "湖南", "city": "衡阳", "address": "湖南衡阳"},
            ]
        }

    def search_single(_args):
        return {
            "results": [
                {
                    "name": "可可托海景区",
                    "uid": "uid-koktokay",
                    "province": "新疆",
                    "city": "阿勒泰",
                    "address": "新疆阿勒泰",
                }
            ]
        }

    def detail_mock(_args):
        return {
            "uid": _args.get("uid"),
            "name": "可可托海景区",
            "address": "新疆阿勒泰富蕴县",
            "price": "90元",
            "shop_hours": "09:00-18:00",
        }

    def weather_mock(_args):
        return {"result": {"now": {"text": "晴", "temp": 5}, "forecasts": [{"text": "小雪"}]}}

    mgr.register_mock_handler("baidu_map", "map_search_places", search_yunfeng)
    mgr.register_mock_handler("baidu_map", "map_geocode", search_single)
    mgr.register_mock_handler("baidu_map", "map_place_details", detail_mock)
    mgr.register_mock_handler("baidu_map", "map_weather", weather_mock)


@pytest.fixture
def baidu_env(monkeypatch):
    settings = _baidu_settings()
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    reset_mcp_client_manager()
    _register_baidu_mocks()
    registry = ToolRegistry()
    yield settings, registry
    reset_mcp_client_manager()


def _yunfeng_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="云峰山什么时候去合适",
        normalized_request="云峰山最佳游玩时间",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", places=["云峰山"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit", "seasonality"],
        confidence=0.85,
        can_answer_with_model_prior=True,
    )


def _ticket_price_frame(place: str = "可可托海景区") -> SemanticFrame:
    return SemanticFrame(
        raw_query=f"{place}票价如何",
        normalized_request=f"{place}门票价格",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="Altay", places=[place]),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=["ticket_price"],
        confidence=0.9,
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )


def _forecast_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="明天去可可托海天气怎么样",
        normalized_request="可可托海明日天气",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="Altay", places=["可可托海"]),
        time_scope=TimeScope.SPECIFIC_DATE,
        information_needs=["forecast", "weather"],
        confidence=0.9,
        requires_live_data=True,
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )


def test_baidu_map_tools_not_configured_without_ak(monkeypatch):
    settings = Settings(mcp_enabled=True, mcp_baidu_map_enabled=True, baidu_map_ak=None)
    for target in (
        "app.config.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    reset_mcp_client_manager()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "baidu_place_search_mcp" not in wl.allowed_tool_names()
    reason = wl.reason_by_tool.get("baidu_place_search_mcp", "")
    assert "BAIDU_MAP_AK" in reason or "missing" in reason.lower()


def test_baidu_place_search_in_whitelist_for_unknown_place(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    assert "baidu_place_search_mcp" in wl.allowed_tool_names()


def test_baidu_detail_in_whitelist_for_ticket_price(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海景区票价如何")
    state.semantic_frame = _ticket_price_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "baidu_place_detail_mcp" in names
    assert "knowledge_prior" not in names


def test_baidu_weather_in_whitelist_for_forecast(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="明天去可可托海天气怎么样")
    state.semantic_frame = _forecast_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    assert "baidu_weather_mcp" in wl.allowed_tool_names()


@pytest.mark.asyncio
async def test_baidu_multiple_candidates_triggers_clarification(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class BaiduSearchController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="baidu_place_search_mcp",
                    arguments={"query": "云峰山"},
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=BaiduSearchController(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    assert out.next_state == "clarification_response"
    assert "多个同名地点" in (out.final_response or "")


def test_baidu_place_detail_price_candidate_not_final_ticket_price():
    ev = Evidence(
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        source_url=None,
        country="China",
        place_name="可可托海景区",
        data_freshness=DataFreshness.RECENT,
        license_scope=LicenseScope.API_ALLOWED,
        confidence=0.65,
        claims=[
            Claim(
                claim_type=ClaimType.PRICE_CANDIDATE,
                value="90元",
                confidence=0.58,
            )
        ],
    )
    sheet = EvidenceAggregator.aggregate("可可托海景区", [ev])
    assert sheet.ticket_price is None


@pytest.mark.asyncio
async def test_baidu_evidence_normalization(baidu_env, monkeypatch):
    settings = baidu_env[0]
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler(
        "baidu_map",
        "map_search_places",
        lambda _a: {
            "results": [
                {
                    "name": "禾木景区",
                    "uid": "uid-hemu",
                    "province": "新疆",
                    "city": "阿勒泰",
                    "address": "新疆阿勒泰布尔津",
                    "lat": 48.5,
                    "lng": 87.0,
                }
            ]
        },
    )
    from tools.mcp.adapters.baidu_map_adapter import BaiduMapMCPAdapter

    evidence = await BaiduMapMCPAdapter("baidu_place_search_mcp", client=mgr).run(
        query="禾木景区",
        country="China",
        place_name="禾木景区",
    )
    assert evidence
    assert evidence[0].source_type == SourceType.MAP
    claim_types = {c.claim_type for c in evidence[0].claims}
    assert ClaimType.POI_UID in claim_types
    assert ClaimType.PLACE_CANDIDATES in claim_types
    assert ClaimType.ADDRESS in claim_types or ClaimType.COORDINATES in claim_types
