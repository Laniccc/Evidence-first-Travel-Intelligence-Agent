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
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_query import TravelAgentState, UserGoal
from app.tools import ToolRegistry
from app.tools.mcp.client_manager import get_mcp_client_manager, reset_mcp_client_manager
from app.tools.tool_name_resolver import resolve_tool_name


def _mcp_settings(**overrides) -> Settings:
    base = {
        "mcp_enabled": True,
        "mcp_search_enabled": True,
        "mcp_search_server_url": "mock://",
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
    }
    base.update(overrides)
    return Settings(**base)


def _register_mcp_mocks(settings: Settings) -> None:
    reset_mcp_client_manager()
    mgr = get_mcp_client_manager(settings)

    def search_mock(args):
        return {
            "country": args.get("country", "China"),
            "city": args.get("city", "Altay"),
            "claims": [
                {
                    "claim_type": "best_time_to_visit",
                    "value": "9-10月秋色最佳",
                    "confidence": 0.78,
                }
            ],
            "confidence": 0.78,
        }

    def climate_mock(args):
        return {
            "country": args.get("country", "Japan"),
            "city": args.get("city", "Hokkaido"),
            "claims": [{"claim_type": "seasonality", "value": "7-8月凉爽", "confidence": 0.8}],
            "confidence": 0.8,
        }

    def wikidata_mock(args):
        return {
            "country": "China",
            "claims": [{"claim_type": "travel_advice", "value": "喀纳斯湖", "confidence": 0.85}],
            "confidence": 0.85,
        }

    def weather_mock(args):
        return {
            "country": "Japan",
            "city": "Sapporo",
            "claims": [{"claim_type": "weather", "value": "snow likely", "confidence": 0.9}],
            "confidence": 0.9,
        }

    mgr.register_mock_handler("search", "public_web_search", search_mock)
    mgr.register_mock_handler("search", "seasonality_search", search_mock)
    mgr.register_mock_handler("openmeteo", "forecast", weather_mock)
    mgr.register_mock_handler("openmeteo", "monthly_climate", climate_mock)
    mgr.register_mock_handler("wikidata", "entity_resolution", wikidata_mock)
    mgr.register_mock_handler("osm", "place_lookup", wikidata_mock)


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
    _register_mcp_mocks(settings_on)
    registry_on = ToolRegistry()
    assert "search_mcp" in registry_on._mcp_tool_names
    assert "openmeteo_mcp" in registry_on._mcp_tool_names


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
    assert "openmeteo_mcp" in names or "climate_mcp" in names
    assert "knowledge_prior" in names
    assert "official_page_reader_mcp" not in names


def test_s5_whitelist_opening_hours_excludes_knowledge_prior():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="清水寺今天几点关门")
    state.semantic_frame = _opening_hours_frame()
    wl = ToolWhitelistBuilder(tools_registry=ToolRegistry()).build(state)
    assert "knowledge_prior" not in wl.allowed_tool_names()
    assert "official" in wl.allowed_tool_names()


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
    assert "wikidata_mcp" in tool_names


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
    assert "openmeteo_mcp" in names or "weather_mcp" in names
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
    assert "wikidata_mcp" in names or "osm_mcp" in names


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
    assert "osm_mcp" in names or "places_mcp" in names
    assert "knowledge_prior" not in names
