"""MCP + S5 whitelist integration tests."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
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
from app.schemas.tool_whitelist import ToolDescriptor
from app.schemas.tool_trace import ToolTrace
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_query import TravelAgentState, UserGoal
from app.tools import ToolRegistry
from app.tools.mcp.client_manager import get_mcp_client_manager, reset_mcp_client_manager
from app.tools.tool_name_resolver import resolve_tool_name


def _mcp_settings(**overrides) -> Settings:
    base = {
        "mcp_profile": "search_only",
        "mcp_enabled": True,
        "mcp_search_enabled": True,
        "mcp_search_server_url": "mock://",
        "mcp_search_transport": "open_websearch_http",
        "mcp_browser_enabled": True,
        "mcp_browser_server_url": "mock://",
        "mcp_osm_enabled": True,
        "mcp_osm_server_url": "mock://",
        "mcp_openmeteo_enabled": True,
        "mcp_openmeteo_server_url": "mock://",
        "mcp_wikipedia_enabled": True,
        "mcp_wikipedia_server_url": "mock://",
        "mcp_wikidata_enabled": True,
        "mcp_wikidata_server_url": "mock://",
        "enable_real_official_page": False,
    }
    base.update(overrides)
    return Settings(**base)


def _register_mcp_mocks(settings: Settings) -> None:
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)

    def search_mock(args):
        return {
            "results": [
                {
                    "title": "喀纳斯湖旅游攻略",
                    "url": "https://example.com/kanas",
                    "snippet": "9-10月秋色最佳",
                }
            ],
            "country": args.get("country", "China"),
            "city": args.get("city", "Altay"),
        }

    def fetch_mock(args):
        return {
            "content": "门票：80元。开放时间 08:30-17:00。",
            "url": args.get("url", "https://example.com/official"),
        }

    def geocoding_mock(_args):
        return {"results": [{"latitude": 43.8, "longitude": 87.6, "name": "喀纳斯湖"}]}

    def forecast_mock(_args):
        return {"daily": {"temperature_2m_max": [5], "precipitation_sum": [2]}}

    def archive_mock(_args):
        return {"daily": {"temperature_2m_mean": [12], "precipitation_sum": [40]}}

    def wikidata_search_mock(args):
        return {"results": [{"id": "Q123", "label": args.get("query", "喀纳斯湖")}]}

    def wikidata_meta_mock(_args):
        return {"labels": {"zh": "喀纳斯湖"}, "descriptions": {"zh": "新疆湖泊"}}

    def wikidata_props_mock(_args):
        return {"P625": "坐标 48.7, 87.0"}

    def osm_geocode_mock(args):
        return f"lat=32.05 lon=118.85 for {args.get('address', '')}"

    def osm_nearby_mock(_args):
        return "nearby: restaurant A, restaurant B"

    def wiki_search_mock(args):
        return {"results": [{"title": args.get("query", "喀纳斯湖")}]}

    def wiki_summary_mock(args):
        return {"extract": f"Summary for {args.get('title', '')}"}

    def browser_nav_mock(_args):
        return {"ok": True}

    def browser_snap_mock(_args):
        return {"content": "Opening hours: 08:30-17:00. Ticket: 80 CNY."}

    for tool in ("public_web_search", "search", "seasonality_search"):
        mgr.register_mock_handler("search", tool, search_mock)
    mgr.register_mock_handler("search", "fetch", fetch_mock)
    mgr.register_mock_handler("search", "fetch-web", fetch_mock)
    mgr.register_mock_handler("openmeteo", "geocoding", geocoding_mock)
    mgr.register_mock_handler("openmeteo", "weather_forecast", forecast_mock)
    mgr.register_mock_handler("openmeteo", "weather_archive", archive_mock)
    mgr.register_mock_handler("openmeteo", "forecast", forecast_mock)
    mgr.register_mock_handler("openmeteo", "monthly_climate", archive_mock)
    mgr.register_mock_handler("wikidata", "search_entity", wikidata_search_mock)
    mgr.register_mock_handler("wikidata", "get_metadata", wikidata_meta_mock)
    mgr.register_mock_handler("wikidata", "get_properties", wikidata_props_mock)
    mgr.register_mock_handler("wikidata", "entity_resolution", wikidata_meta_mock)
    mgr.register_mock_handler("osm", "geocode_address", osm_geocode_mock)
    mgr.register_mock_handler("osm", "find_nearby_places", osm_nearby_mock)
    mgr.register_mock_handler("osm", "place_lookup", osm_geocode_mock)
    mgr.register_mock_handler("wikipedia", "wikipedia_search", wiki_search_mock)
    mgr.register_mock_handler("wikipedia", "wikipedia_get_summary", wiki_summary_mock)
    mgr.register_mock_handler("browser", "browser_navigate", browser_nav_mock)
    mgr.register_mock_handler("browser", "browser_snapshot", browser_snap_mock)
    mgr.register_mock_handler("sqlite", "read_records", lambda _a: [])
    mgr.register_mock_handler("sqlite", "query", lambda _a: [])


def _patch_search_only_settings(monkeypatch, **overrides) -> Settings:
    settings = _mcp_settings(**overrides)
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
        "app.orchestrator.evidence_policy_guard.get_settings",
    ):
        monkeypatch.setattr(target, lambda _s=settings: _s)
    reset_mcp_client_manager()
    return settings


@pytest.fixture
def mcp_full_env(monkeypatch):
    settings = _mcp_settings(mcp_profile="full", mcp_enable_all=True)
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
        "app.orchestrator.evidence_policy_guard.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    _register_mcp_mocks(settings)
    registry = ToolRegistry()
    yield settings, registry
    reset_mcp_client_manager()


@pytest.fixture
def mcp_env(monkeypatch):
    settings = _mcp_settings()
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
        "app.orchestrator.evidence_policy_guard.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    _register_mcp_mocks(settings)
    registry = ToolRegistry()
    yield settings, registry
    reset_mcp_client_manager()


def _kanas_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="喀纳斯湖适合几月份去",
        normalized_request="喀纳斯湖最佳出行月份",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", city="Altay", places=["喀纳斯湖"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit", "seasonality"],
        confidence=0.9,
        requires_live_data=False,
        requires_exact_fact=False,
        can_answer_with_model_prior=True,
    )


def _hokkaido_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="北海道适合几月份去",
        normalized_request="北海道最佳出行月份",
        query_scope=QueryScope.REGION,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="Japan", city="Hokkaido", places=[]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit", "seasonality"],
        confidence=0.9,
        requires_live_data=False,
        requires_exact_fact=False,
        can_answer_with_model_prior=True,
    )


def _opening_hours_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="清水寺今天几点关门",
        normalized_request="清水寺今日闭馆时间",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="Japan", city="Kyoto", places=["清水寺"]),
        time_scope=TimeScope.CURRENT,
        information_needs=["opening_hours"],
        confidence=0.9,
        requires_live_data=True,
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )


def _weather_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="札幌明天会不会下雪",
        normalized_request="札幌明日降雪",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="Japan", city="Sapporo", places=["札幌"]),
        time_scope=TimeScope.SPECIFIC_DATE,
        information_needs=["forecast", "weather"],
        confidence=0.9,
        requires_live_data=True,
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )


def _nearby_food_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="附近有没有适合吃饭休息的地方",
        normalized_request="附近餐饮休息",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="Japan", city="Kyoto", places=["清水寺"]),
        time_scope=TimeScope.CURRENT,
        information_needs=["nearby_food", "nearby_rest_area"],
        confidence=0.85,
        requires_live_data=True,
        requires_exact_fact=False,
        can_answer_with_model_prior=False,
    )


def test_mcp_tools_registered_only_when_configured(monkeypatch):
    settings_off = Settings(mcp_enabled=False)
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.tools.mcp.client_manager.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings_off)
    reset_mcp_client_manager()
    registry = ToolRegistry()
    assert not registry._mcp_tool_names

    settings_on = _mcp_settings()
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.tools.mcp.client_manager.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings_on)
    reset_mcp_client_manager()
    _register_mcp_mocks(settings_on)
    registry_on = ToolRegistry()
    assert "search_mcp" in registry_on._mcp_tool_names
    assert "official_page_reader_mcp" in registry_on._mcp_tool_names
    for name in (
        "openmeteo_mcp",
        "browser_mcp",
        "osm_mcp",
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "baidu_weather_mcp",
    ):
        assert name not in registry_on._mcp_tool_names


def test_unconfigured_mcp_not_exposed_to_s5(monkeypatch):
    settings = Settings(mcp_enabled=False)
    monkeypatch.setattr("app.orchestrator.tool_whitelist_builder.get_settings", lambda: settings)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    exposed = set(wl.allowed_tool_names())
    for name in ("search_mcp", "openmeteo_mcp", "wikidata_mcp", "browser_mcp"):
        assert name not in exposed


def test_s5_whitelist_best_time_to_visit(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "search_mcp" in names
    assert "knowledge_prior" in names
    assert "official_page_reader_mcp" not in names
    assert "browser_mcp" not in names
    assert "openmeteo_mcp" not in names


def test_s5_whitelist_opening_hours_excludes_knowledge_prior(monkeypatch):
    _patch_search_only_settings(monkeypatch)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "knowledge_prior" not in wl.allowed_tool_names()
    assert "official" not in wl.allowed_tool_names()
    assert "search_mcp" in wl.allowed_tool_names()


@pytest.mark.asyncio
async def test_s5_llm_can_choose_search_mcp(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class SearchController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if policy.state_name == "evidence_planning_and_tool_use" and step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="search_mcp",
                    arguments={"query": "喀纳斯湖 最佳旅游时间"},
                    reason_summary="公开资料",
                    confidence=0.82,
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=SearchController(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    assert any(t.tool_name == "search_mcp" for t in out.tool_traces)
    assert out.evidence


@pytest.mark.asyncio
async def test_s5_llm_can_call_multiple_mcp_tools(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class MultiMcpController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if policy.state_name != "evidence_planning_and_tool_use":
                return AgentAction(action_type=AgentActionType.FINISH_STATE)
            if step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="search_mcp",
                    arguments={"query": "喀纳斯湖 月份"},
                )
            if step == 1:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="wikidata_mcp",
                    arguments={"query": "喀纳斯湖"},
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=MultiMcpController(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    tool_names = {t.tool_name for t in out.tool_traces}
    assert "search_mcp" in tool_names
    assert len(tool_names) >= 1


def test_policy_guard_rejects_non_whitelisted_mcp():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="wikipedia_mcp")
    with pytest.raises(ValueError, match="not in dynamic whitelist"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_policy_guard_rejects_unconfigured_mcp(monkeypatch):
    settings = Settings(mcp_enabled=True, mcp_search_enabled=True, mcp_search_server_url="")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.orchestrator.tool_whitelist_builder.get_settings", lambda: settings)
    monkeypatch.setattr("app.orchestrator.evidence_policy_guard.get_settings", lambda: settings)
    reset_mcp_client_manager()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    wl.allowed_tools.append(
        ToolDescriptor(name="search_mcp", description="test", configured=True)
    )
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.CALL_TOOL, target="search_mcp")
    with pytest.raises(ValueError, match="Unconfigured MCP"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_knowledge_prior_forbidden_for_ticket_price():
    frame = SemanticFrame(
        raw_query="门票多少钱",
        normalized_request="门票",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="Japan", city="Kyoto", places=["清水寺"]),
        time_scope=TimeScope.CURRENT,
        information_needs=["ticket_price"],
        confidence=0.9,
        requires_exact_fact=True,
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="门票多少钱")
    state.semantic_frame = frame
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "knowledge_prior" not in wl.allowed_tool_names()
    guard = EvidencePolicyGuard()
    wl.allowed_tools.append(ToolDescriptor(name="knowledge_prior", description="t", configured=True))
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="knowledge_prior",
        arguments={"information_need": "ticket_price"},
    )
    with pytest.raises(ValueError, match="knowledge_prior cannot satisfy"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_openmeteo_selected_for_weather_query(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="札幌明天会不会下雪")
    state.semantic_frame = _weather_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "weather" in names
    assert "openmeteo_mcp" not in names
    assert "knowledge_prior" not in names


def test_osm_or_wikidata_used_for_entity_resolution(mcp_env):
    _, registry = mcp_env
    frame = SemanticFrame(
        raw_query="喀纳斯湖在哪里",
        normalized_request="地点确认",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["喀纳斯湖"]),
        time_scope=TimeScope.CURRENT,
        information_needs=["entity_resolution"],
        confidence=0.9,
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖在哪里")
    state.semantic_frame = frame
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "search_mcp" in names
    assert "wikidata_mcp" not in names
    assert "osm_mcp" not in names


@pytest.mark.asyncio
async def test_tool_trace_marks_selected_by_llm(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class LlmSearchController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            prompt_context["_last_action_source"] = "llm"
            if policy.state_name == "evidence_planning_and_tool_use" and step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="search_mcp",
                    arguments={"query": state.raw_user_query},
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {
        "tool_whitelist": wl,
        "allowed_tools": [t.model_dump() for t in wl.allowed_tools],
        "loop_state_name": "evidence_planning_and_tool_use",
    }
    out = await ClaudeStateRunner(model_controller=LlmSearchController(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    assert out.tool_traces
    assert any(
        t.tool_name == "search_mcp" and t.selected_by_llm and t.whitelist_checked
        for t in out.tool_traces
    )
    assert any(t.requested_by_state == "evidence_planning_and_tool_use" for t in out.tool_traces)


@pytest.mark.asyncio
async def test_s5_finishes_when_evidence_sufficient(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="喀纳斯湖适合几月份去")
    state.semantic_frame = _kanas_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class FinishAfterSearch(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="search_mcp",
                    arguments={"query": "喀纳斯湖"},
                )
            return AgentAction(
                action_type=AgentActionType.FINISH_STATE,
                arguments={"evidence_gap_acknowledged": True},
            )

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=FinishAfterSearch(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    assert out.evidence_planning_completed
    assert out.evidence


@pytest.mark.asyncio
async def test_s5_fallback_to_knowledge_prior_when_allowed_and_tools_fail(monkeypatch):
    settings = _mcp_settings(mcp_search_server_url="mock://")
    monkeypatch.setattr("app.orchestrator.evidence_policy_guard.get_settings", lambda: settings)
    for target in (
        "app.config.get_settings",
        "app.tools.mcp.registry_setup.get_settings",
        "app.tools.mcp.client_manager.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler(
        "search",
        "public_web_search",
        lambda _a: (_ for _ in ()).throw(RuntimeError("search down")),
    )
    registry = ToolRegistry()

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="北海道适合几月份去")
    state.semantic_frame = _hokkaido_frame()
    state.travel_task = TravelTask(task_type=TravelTaskType.OPEN_ENDED_ADVICE, country="Japan", city="Hokkaido")
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.MODEL_PRIOR_ALLOWED,
        allow_knowledge_prior=True,
        reason="seasonal",
    )
    state.user_goal = UserGoal(destination_country="Japan", destination_city="Hokkaido")
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class PriorFallback(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="search_mcp",
                    arguments={"query": "北海道"},
                )
            if step == 1:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="knowledge_prior",
                    arguments={"information_need": "best_time_to_visit"},
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=PriorFallback(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    assert any(t.tool_name == "knowledge_prior" for t in out.tool_traces)


def test_strong_fact_does_not_fallback_to_knowledge_prior():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "knowledge_prior" not in wl.allowed_tool_names()


def test_nearby_food_whitelist(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="附近有没有适合吃饭休息的地方")
    state.semantic_frame = _nearby_food_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "restaurant" in names
    assert "search_mcp" in names
    assert "osm_mcp" not in names
    assert "places_mcp" not in names


def _hemu_ticket_price_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="禾木景区票价如何？",
        normalized_request="禾木景区门票价格",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="Altay", places=["禾木景区"]),
        time_scope=TimeScope.FLEXIBLE,
        information_needs=["ticket_price"],
        confidence=0.9,
        requires_live_data=False,
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )


def test_ticket_price_whitelist_includes_search_when_configured(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "search_mcp" in names
    assert "official_page_reader_mcp" in names
    assert "official" not in names
    assert "browser_mcp" not in names
    assert "places" not in names
    assert "transit" not in names


def test_ticket_price_whitelist_blocks_knowledge_prior():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "knowledge_prior" not in wl.allowed_tool_names()
    assert "knowledge_prior" in wl.blocked_tools or "knowledge_prior" in wl.reason_by_tool


def test_unconfigured_mcp_shows_block_reason(monkeypatch):
    settings = Settings(mcp_enabled=True, mcp_profile="off", mcp_enable_all=False)
    for target in (
        "app.config.get_settings",
        "app.orchestrator.tool_whitelist_builder.get_settings",
        "app.tools.mcp.client_manager.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)
    reset_mcp_client_manager()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "search_mcp" not in wl.allowed_tool_names()
    reason = wl.reason_by_tool.get("search_mcp", "")
    assert "MCP_SEARCH_ENABLED=false" in reason or "false" in reason.lower()


@pytest.mark.asyncio
async def test_open_websearch_adapter_returns_evidence(monkeypatch):
    settings = Settings(
        mcp_enabled=True,
        mcp_search_enabled=True,
        mcp_search_server_url="mock://",
        mcp_search_transport="open_websearch_http",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler(
        "search",
        "search",
        lambda _a: {
            "results": [
                {
                    "title": "禾木景区官网门票",
                    "url": "https://www.gov.cn/hemu-ticket",
                    "snippet": "门票价格请以景区公示为准",
                }
            ]
        },
    )
    from tools.mcp.adapters.search_mcp_adapter import SearchMCPAdapter

    adapter = SearchMCPAdapter(client=mgr)
    evidence = await adapter.run(
        query="禾木景区票价",
        country="China",
        city="Altay",
        place_name="禾木景区",
        information_need="ticket_price",
    )
    assert evidence
    assert evidence[0].source_name == "open-webSearch"
    assert any(c.claim_type == ClaimType.TICKET_PRICE for c in evidence[0].claims)


def test_evidence_required_ticket_price_cannot_finish_before_search_attempt(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.EVIDENCE_REQUIRED,
        allow_knowledge_prior=False,
        reason="ticket price",
    )
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.FINISH_STATE, arguments={})
    with pytest.raises(ValueError, match="not yet attempted"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


def test_evidence_required_ticket_price_can_finish_after_all_tools_fail_with_ack(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.EVIDENCE_REQUIRED,
        allow_knowledge_prior=False,
        reason="ticket price",
    )
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    for tool in wl.allowed_tool_names():
        state.tool_traces.append(
            ToolTrace(
                tool_name=tool,
                input={},
                evidence_ids=[],
                status="ok",
            )
        )
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.FINISH_STATE,
        arguments={
            "evidence_gap_acknowledged": True,
            "limitations": ["已尝试 official/search/browser/places，但未获取到可验证票价证据"],
        },
    )
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=wl)


@pytest.mark.asyncio
async def test_he_mu_ticket_price_uses_search_mcp_when_available(mcp_env):
    _, registry = mcp_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    state.answer_mode_decision = AnswerModeDecision(
        answer_mode=AnswerMode.EVIDENCE_REQUIRED,
        allow_knowledge_prior=False,
        reason="ticket price",
    )
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)

    class TicketSearchController(ActionModelController):
        async def next_action(self, state, policy, prompt_context, step):
            if policy.state_name == "evidence_planning_and_tool_use" and step == 0:
                return AgentAction(
                    action_type=AgentActionType.CALL_TOOL,
                    target="search_mcp",
                    arguments={"query": state.raw_user_query},
                )
            if step == 1:
                return AgentAction(
                    action_type=AgentActionType.FINISH_STATE,
                    arguments={"evidence_gap_acknowledged": True},
                )
            return AgentAction(action_type=AgentActionType.FINISH_STATE)

    ctx = {"tool_whitelist": wl, "allowed_tools": [t.model_dump() for t in wl.allowed_tools]}
    out = await ClaudeStateRunner(model_controller=TicketSearchController(), tools=registry).run(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx
    )
    assert any(t.tool_name == "search_mcp" for t in out.tool_traces)


def test_stub_mcp_tools_blocked_from_ticket_price_whitelist(monkeypatch):
    _patch_search_only_settings(monkeypatch)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="禾木景区票价如何？")
    state.semantic_frame = _hemu_ticket_price_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "browser_mcp" not in wl.allowed_tool_names()
    assert "official_page_reader_mcp" in wl.allowed_tool_names()
    assert "MCP_BROWSER_ENABLED=false" in wl.reason_by_tool.get("browser_mcp", "") or "browser" in wl.reason_by_tool.get("browser_mcp", "").lower()
    assert "ENABLE_REAL_OFFICIAL_PAGE=false" in wl.reason_by_tool.get("official", "")


@pytest.mark.parametrize(
    "need",
    ["ticket_price", "opening_hours", "weather_today", "current_crowd"],
)
def test_strong_fact_still_does_not_use_knowledge_prior(need):
    frame = SemanticFrame(
        raw_query="test",
        normalized_request="test",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="Japan", city="Kyoto", places=["清水寺"]),
        time_scope=TimeScope.CURRENT,
        information_needs=[need],
        confidence=0.9,
        requires_exact_fact=True,
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    state.semantic_frame = frame
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "knowledge_prior" not in wl.allowed_tool_names()


@pytest.mark.asyncio
async def test_http_mcp_autostart_skips_when_healthy(monkeypatch):
    from tools.mcp import http_autostart

    http_autostart.reset_http_autostart_state()
    settings = Settings(
        mcp_enabled=True,
        mcp_http_autostart=True,
        mcp_search_enabled=True,
        mcp_search_server_url="http://127.0.0.1:3210",
        mcp_search_transport="open_websearch_http",
        mcp_openmeteo_enabled=False,
    )

    async def fake_ok(_url: str, timeout: float = 3.0) -> bool:
        return True

    monkeypatch.setattr(http_autostart, "_http_ok", fake_ok)

    notes = await http_autostart.ensure_http_mcp_services(settings)
    assert any("already healthy" in n for n in notes)


@pytest.mark.asyncio
async def test_http_mcp_autostart_disabled(monkeypatch):
    from tools.mcp import http_autostart

    http_autostart.reset_http_autostart_state()
    settings = Settings(mcp_enabled=True, mcp_http_autostart=False)
    spawned: list[str] = []
    monkeypatch.setattr(http_autostart, "_spawn_detached", lambda cmd, new_window=True: spawned.append(cmd) or True)

    notes = await http_autostart.ensure_http_mcp_services(settings)
    assert notes == []
    assert spawned == []


@pytest.mark.asyncio
async def test_http_mcp_autostart_kills_stale_before_spawn(monkeypatch):
    from tools.mcp import http_autostart

    http_autostart.reset_http_autostart_state()
    settings = Settings(
        mcp_enabled=True,
        mcp_http_autostart=True,
        mcp_http_autostart_kill_stale=True,
        mcp_search_enabled=True,
        mcp_search_server_url="http://127.0.0.1:3210",
        mcp_search_transport="open_websearch_http",
        mcp_openmeteo_enabled=False,
    )
    port_open = True

    monkeypatch.setattr(http_autostart, "_port_listening", lambda _h, _p, timeout=1.0: port_open)

    async def fake_ok(_url: str, timeout: float = 3.0) -> bool:
        return False

    monkeypatch.setattr(http_autostart, "_http_ok", fake_ok)

    async def cleanup(_host: str, _port: int, *, wait_seconds: float = 3.0) -> list[int]:
        nonlocal port_open
        port_open = False
        return [7728]

    monkeypatch.setattr(http_autostart, "_cleanup_stale_listeners", cleanup)
    spawned: list[str] = []
    monkeypatch.setattr(
        http_autostart,
        "_spawn_detached",
        lambda cmd, new_window=True: spawned.append(cmd) or True,
    )
    async def wait_healthy(_url: str, _ws: float) -> bool:
        return True

    monkeypatch.setattr(http_autostart, "_wait_until_healthy", wait_healthy)

    notes = await http_autostart.ensure_http_mcp_services(settings)
    assert any("killed stale PIDs" in n for n in notes)
    assert any("autostarted" in n for n in notes)
    assert spawned


@pytest.mark.asyncio
async def test_official_page_fetch_adapter_returns_ticket_claim(monkeypatch):
    settings = Settings(
        mcp_enabled=True,
        mcp_search_enabled=True,
        mcp_search_server_url="mock://",
        mcp_search_transport="open_websearch_http",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler(
        "search",
        "fetch",
        lambda _a: {"content": "门票：80元。开放时间 08:30-17:00"},
    )
    from tools.mcp.adapters.official_page_fetch_adapter import OfficialPageFetchAdapter

    evidence = await OfficialPageFetchAdapter(client=mgr).run(
        url="https://example.gov/ticket",
        country="China",
        city="Nanjing",
        place_name="中山陵",
        information_need="ticket_price",
    )
    assert evidence
    assert any(c.claim_type == ClaimType.TICKET_PRICE for c in evidence[0].claims)


@pytest.mark.asyncio
async def test_browser_mcp_adapter_mock_snapshot(monkeypatch):
    settings = Settings(
        mcp_enabled=True,
        mcp_profile="full",
        mcp_browser_enabled=True,
        mcp_browser_server_url="mock://",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler("browser", "browser_navigate", lambda _a: {"ok": True})
    mgr.register_mock_handler(
        "browser",
        "browser_snapshot",
        lambda _a: "Ticket price: 80 CNY. Hours 08:30-17:00",
    )
    from tools.mcp.adapters.browser_mcp_adapter import BrowserMCPAdapter

    evidence = await BrowserMCPAdapter(client=mgr).run(
        url="https://example.com/page",
        information_need="ticket_price",
        country="China",
    )
    assert evidence
    assert evidence[0].claims


@pytest.mark.asyncio
async def test_openmeteo_adapter_weather_mcp(monkeypatch):
    settings = Settings(
        mcp_enabled=True,
        mcp_profile="full",
        mcp_openmeteo_enabled=True,
        mcp_openmeteo_server_url="mock://",
        mcp_openmeteo_transport="streamable_http",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler(
        "openmeteo",
        "geocoding",
        lambda _a: {"results": [{"latitude": 43.06, "longitude": 141.35}]},
    )
    mgr.register_mock_handler(
        "openmeteo",
        "weather_forecast",
        lambda _a: {"daily": {"temperature_2m_max": [-1], "precipitation_sum": [5]}},
    )
    from tools.mcp.adapters.openmeteo_mcp_adapter import OpenMeteoMCPAdapter

    evidence = await OpenMeteoMCPAdapter("weather_mcp", client=mgr).run(
        city="Sapporo",
        country="Japan",
        information_need="weather",
    )
    assert evidence
    assert evidence[0].claims[0].claim_type == ClaimType.WEATHER


def test_openmeteo_whitelist_with_full_profile(mcp_full_env):
    _, registry = mcp_full_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="札幌明天会不会下雪")
    state.semantic_frame = _weather_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "weather_mcp" in names or "openmeteo_mcp" in names


def test_nearby_food_whitelist_with_full_profile(mcp_full_env):
    _, registry = mcp_full_env
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="附近有没有适合吃饭休息的地方")
    state.semantic_frame = _nearby_food_frame()
    wl = ToolWhitelistBuilder(tools_registry=registry).build(state)
    names = set(wl.allowed_tool_names())
    assert "places_mcp" in names or "osm_mcp" in names


@pytest.mark.asyncio
async def test_osm_geocode_adapter_mock(monkeypatch):
    settings = Settings(mcp_enabled=True, mcp_profile="full", mcp_osm_enabled=True, mcp_osm_server_url="mock://")
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)
    mgr.register_mock_handler("osm", "geocode_address", lambda a: f"coords for {a.get('address')}")

    from tools.mcp.adapters.osm_mcp_adapter import OsmMCPAdapter

    evidence = await OsmMCPAdapter("geocode_mcp", client=mgr).run(
        place_name="中山陵",
        city="Nanjing",
        country="China",
    )
    assert evidence


def test_policy_to_upstream_covers_implemented_policies():
    from tools.mcp.adapter_status import IMPLEMENTED_MCP_POLICIES, POLICY_TO_UPSTREAM

    for policy in IMPLEMENTED_MCP_POLICIES:
        assert policy in POLICY_TO_UPSTREAM
        assert POLICY_TO_UPSTREAM[policy]

