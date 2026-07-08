"""Baidu Map MCP P0–P4 integration tests (17 items)."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.evidence_aggregator import EvidenceAggregator
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder, location_usage_allowed
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
from app.schemas.user_query import TravelAgentState, UserContext
from app.tools import ToolRegistry
from app.tools.mcp.adapter_status import IMPLEMENTED_MCP_POLICIES
from app.tools.mcp.client_manager import get_mcp_client_manager, reset_mcp_client_manager
from tools.mcp.registry_setup import attach_mcp_tools


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
                    "lat": 47.0,
                    "lng": 89.0,
                }
            ]
        }

    def detail_mock(args):
        return {
            "uid": args.get("uid"),
            "name": "可可托海景区",
            "address": "新疆阿勒泰富蕴县",
            "price": "90元",
            "shop_hours": "09:00-18:00",
        }

    def weather_mock(_args):
        return {"result": {"now": {"text": "晴", "temp": 5}, "forecasts": [{"text": "小雪"}]}}

    def geocode_mock(_args):
        return {"result": {"location": {"lat": 47.2, "lng": 89.1}, "formatted_address": "新疆阿勒泰"}}

    def reverse_mock(_args):
        return {"result": {"formatted_address": "新疆阿勒泰", "addressComponent": {"city": "阿勒泰"}}}

    def directions_mock(_args):
        return {"result": {"routes": [{"distance": 120000, "duration": 5400, "steps": [{"instruction": "出发"}]}]}}

    def matrix_mock(_args):
        return {"result": {"distances": [[1000, 2000]], "durations": [[600, 1200]]}}

    def traffic_mock(_args):
        return {"result": {"evaluation": "拥堵", "congestion": 0.8}}

    def ip_mock(_args):
        return {"result": {"content": {"address_detail": {"city": "北京", "province": "北京"}, "point": {"x": 116.4, "y": 39.9}}}}

    def search_handler(args):
        q = str(args.get("query") or args.get("address") or "")
        if "云峰" in q:
            return search_yunfeng(args)
        if "白沙湖" in q:
            if args.get("region"):
                return {
                    "results": [
                        {
                            "name": "白沙湖",
                            "uid": "uid-baisha",
                            "city": "阿勒泰",
                            "province": "新疆",
                            "lat": 47.1,
                            "lng": 87.5,
                        }
                    ]
                }
            return {
                "results": [
                    {
                        "name": "白沙湖",
                        "city": "阿勒泰",
                        "province": "新疆",
                        "lat": 47.1,
                        "lng": 87.5,
                        "address": "新疆阿勒泰",
                    }
                ]
            }
        return search_single(args)

    mgr.register_mock_handler("baidu_map", "map_search_places", search_handler)
    mgr.register_mock_handler("baidu_map", "map_geocode", geocode_mock)
    mgr.register_mock_handler("baidu_map", "map_reverse_geocode", reverse_mock)
    mgr.register_mock_handler("baidu_map", "map_place_details", detail_mock)
    mgr.register_mock_handler("baidu_map", "map_weather", weather_mock)
    mgr.register_mock_handler("baidu_map", "map_directions", directions_mock)
    mgr.register_mock_handler("baidu_map", "map_directions_matrix", matrix_mock)
    mgr.register_mock_handler("baidu_map", "map_road_traffic", traffic_mock)
    mgr.register_mock_handler("baidu_map", "map_ip_location", ip_mock)


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
    attach_mcp_tools(registry)
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


def _route_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="从乌鲁木齐到可可托海自驾怎么走",
        normalized_request="乌鲁木齐到可可托海路线",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["可可托海"]),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=["route_plan", "transport_planning"],
        confidence=0.9,
        requires_exact_fact=False,
    )


def _traffic_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="独库公路现在路况怎么样",
        normalized_request="独库公路路况",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["独库公路"]),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=["road_traffic", "traffic_status"],
        confidence=0.9,
        requires_live_data=True,
    )


# 1
def test_baidu_tools_not_configured_without_ak(monkeypatch):
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


# 2
def test_baidu_p0_tools_registered_with_ak(baidu_env):
    _, registry = baidu_env
    for tool in ("baidu_place_search_mcp", "baidu_place_detail_mcp", "baidu_weather_mcp"):
        assert getattr(registry, tool, None) is not None


# 3–6 P1–P4 registration
@pytest.mark.parametrize(
    "policy",
    [
        "baidu_geocode_mcp",
        "baidu_reverse_geocode_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
        "baidu_ip_location_mcp",
    ],
)
def test_baidu_p1_p4_tools_registered_and_implemented(baidu_env, policy):
    _, registry = baidu_env
    assert policy in IMPLEMENTED_MCP_POLICIES
    assert getattr(registry, policy, None) is not None


# 7
def test_baidu_ip_location_requires_location_permission(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="推荐景点")
    state.semantic_frame = SemanticFrame(
        raw_query="推荐景点",
        normalized_request="推荐景点",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.GENERAL_ADVICE,
        entities=SemanticEntities(country="China"),
        information_needs=["nearby_food"],
    )
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    assert "baidu_ip_location_mcp" not in wl.allowed_tool_names()

    wl_allowed = ToolWhitelistBuilder(tools_registry=registry).build(
        state,
        {"user_ctx": UserContext(location_usage_allowed=True)},
    )
    assert "baidu_ip_location_mcp" in wl_allowed.allowed_tool_names()


# 8
def test_baidu_place_search_in_whitelist_for_unknown_place(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    assert "baidu_place_search_mcp" in wl.allowed_tool_names()


# 9
def test_baidu_detail_in_whitelist_for_ticket_price(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海景区票价如何")
    state.semantic_frame = _ticket_price_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "baidu_place_detail_mcp" in names
    assert "knowledge_prior" not in names


# 10
def test_baidu_weather_in_whitelist_for_forecast(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="明天去可可托海天气怎么样")
    state.semantic_frame = _forecast_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    assert "baidu_weather_mcp" in wl.allowed_tool_names()


# 11 route + traffic whitelist
def test_baidu_route_and_traffic_in_whitelist(baidu_env):
    _, registry = baidu_env
    route_state = TravelAgentState(session_id="s", query_id="q", raw_user_query="乌鲁木齐到可可托海路线")
    route_state.semantic_frame = _route_frame()
    route_wl = ToolWhitelistBuilder(tools_registry=registry).build(route_state)
    assert "baidu_route_mcp" in route_wl.allowed_tool_names()

    traffic_state = TravelAgentState(session_id="s", query_id="q", raw_user_query="独库公路路况")
    traffic_state.semantic_frame = _traffic_frame()
    traffic_wl = ToolWhitelistBuilder(tools_registry=registry).build(traffic_state)
    assert "baidu_traffic_mcp" in traffic_wl.allowed_tool_names()


# 12
@pytest.mark.asyncio
async def test_baidu_multiple_candidates_marks_disambiguation_pending(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class EntityResolutionController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_SUBAGENT,
                    target="entity_resolution_agent",
                    arguments={
                        "lookup_intent": "锚定云峰山",
                        "search_query": "云峰山",
                        "anchor_keywords": ["云峰山"],
                    },
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=EntityResolutionController(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    structured = out.structured_result or {}
    assert structured.get("place_disambiguation_pending") is True
    assert len(structured.get("place_disambiguation_candidates") or []) == 2
    claim_types = {c.claim_type for ev in out.evidence for c in ev.claims}
    assert ClaimType.PLACE_CANDIDATES in claim_types
    assert ClaimType.POI_UID not in claim_types


# 13
def test_baidu_price_candidate_not_final_official_ticket_price():
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


# 14
def test_baidu_weather_not_used_for_long_term_best_month(baidu_env):
    _, registry = baidu_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    contract = ResponseContractCompiler().compile(state.semantic_frame)
    weather_tools = {"baidu_weather_mcp", "weather_mcp"}
    for claim in contract.claim_requirements:
        if claim.claim_type in ("best_time_to_visit", "seasonality", "general_seasonal_context"):
            assert not (weather_tools & set(claim.preferred_tools))


# 15
def test_coordinates_are_resolved_before_openmeteo(baidu_env):
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="明天去可可托海天气怎么样")
    state.semantic_frame = _forecast_frame()
    controller = ActionModelController()
    queue = controller._evidence_tool_queue(state, {})
    geo_idx = next((i for i, t in enumerate(queue) if t == "baidu_geocode_mcp"), None)
    meteo_idx = next((i for i, t in enumerate(queue) if t == "openmeteo_mcp"), None)
    assert geo_idx is not None
    assert meteo_idx is not None
    assert geo_idx < meteo_idx

    called = {"baidu_place_search_mcp", "baidu_place_detail_mcp"}
    allowed = set(queue)
    next_tool = next((tool for tool in queue if tool not in called), None)
    if next_tool in {"openmeteo_mcp", "climate_mcp"} and controller._needs_coordinate_resolution(state):
        if "baidu_geocode_mcp" in allowed and "baidu_geocode_mcp" not in called:
            next_tool = "baidu_geocode_mcp"
    assert next_tool == "baidu_geocode_mcp"


# 16
def test_ip_location_not_called_without_permission():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="推荐餐厅")
    assert not location_usage_allowed(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="baidu_ip_location_mcp")
    with pytest.raises(ValueError, match="location_usage_allowed"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


# 17
@pytest.mark.asyncio
async def test_baidu_evidence_normalization(baidu_env, monkeypatch):
    settings = baidu_env[0]
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    mgr = get_mcp_client_manager(settings)
    from tools.mcp.adapters.baidu_map_adapter import BaiduMapMCPAdapter

    search_ev = await BaiduMapMCPAdapter("baidu_place_search_mcp", client=mgr).run(
        query="禾木景区",
        country="China",
        place_name="禾木景区",
    )
    assert search_ev[0].source_type == SourceType.MAP
    search_types = {c.claim_type for c in search_ev[0].claims}
    assert ClaimType.POI_UID in search_types
    assert ClaimType.PLACE_CANDIDATES in search_types

    geo_ev = await BaiduMapMCPAdapter("baidu_geocode_mcp", client=mgr).run(
        address="可可托海",
        country="China",
    )
    geo_types = {c.claim_type for c in geo_ev[0].claims}
    assert ClaimType.COORDINATES in geo_types

    route_ev = await BaiduMapMCPAdapter("baidu_route_mcp", client=mgr).run(
        origin="乌鲁木齐",
        destination="可可托海",
    )
    route_types = {c.claim_type for c in route_ev[0].claims}
    assert ClaimType.DISTANCE in route_types
    assert ClaimType.DURATION in route_types

    traffic_ev = await BaiduMapMCPAdapter("baidu_traffic_mcp", client=mgr).run(road_name="独库公路")
    traffic_types = {c.claim_type for c in traffic_ev[0].claims}
    assert ClaimType.TRAFFIC_STATUS in traffic_types


@pytest.mark.asyncio
async def test_ambiguous_search_omits_top_uid_and_coordinates(baidu_env, monkeypatch):
    settings = baidu_env[0]
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    mgr = get_mcp_client_manager(settings)
    from tools.mcp.adapters.baidu_map_adapter import BaiduMapMCPAdapter

    search_ev = await BaiduMapMCPAdapter("baidu_place_search_mcp", client=mgr).run(
        query="云峰山",
        country="China",
        place_name="云峰山",
    )
    types = {c.claim_type for c in search_ev[0].claims}
    assert ClaimType.PLACE_CANDIDATES in types
    assert ClaimType.POI_UID not in types
    assert ClaimType.COORDINATES not in types


def test_build_map_search_places_args_nearby_and_tag():
    from tools.mcp.adapters.baidu_response_parser import build_map_search_places_args

    nearby = build_map_search_places_args(
        {
            "query": "餐厅",
            "latitude": 47.0,
            "longitude": 89.0,
            "radius": 1500,
            "tag": "美食",
            "nearby_search": True,
        }
    )
    assert nearby["location"] == "47.0,89.0"
    assert nearby["radius"] == 1500
    assert nearby["tag"] == "美食"
    assert "region" not in nearby

    regional = build_map_search_places_args({"query": "五彩滩", "region": "阿勒泰"})
    assert regional["region"] == "阿勒泰"
    assert "location" not in regional


@pytest.mark.asyncio
async def test_detail_resolves_uid_via_reverse_geocode_and_region_search(baidu_env, monkeypatch):
    settings = baidu_env[0]
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    mgr = get_mcp_client_manager(settings)
    from tools.mcp.adapters.baidu_map_adapter import BaiduMapMCPAdapter
    from tools.mcp.adapters.baidu_response_parser import search_claims

    coords_only = search_claims(
        [
            {
                "name": "白沙湖",
                "city": "阿勒泰",
                "province": "新疆",
                "latitude": 47.1,
                "longitude": 87.5,
            }
        ]
    )
    prior = Evidence(
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        place_name="白沙湖",
        claims=coords_only,
    )
    detail_ev = await BaiduMapMCPAdapter("baidu_place_detail_mcp", client=mgr).run(
        place_name="白沙湖",
        prior_evidence=[prior],
    )
    types = {c.claim_type for c in detail_ev[0].claims}
    assert ClaimType.PRICE_CANDIDATE in types or ClaimType.OPENING_HOURS_CANDIDATE in types


def test_orchestrator_fallback_entity_resolution_first():
    from app.agents.s5_evidence_orchestrator_agent import S5EvidenceOrchestratorAgent

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="云峰山什么时候去合适")
    state.semantic_frame = _yunfeng_frame()
    agent = S5EvidenceOrchestratorAgent()
    action = agent._deterministic_fallback(state, {}, step=1)
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "entity_resolution_agent"
