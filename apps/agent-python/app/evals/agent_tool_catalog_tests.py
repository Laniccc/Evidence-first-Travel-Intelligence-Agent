"""Tests for Claude-style agent tool catalog and S5 route queue injection."""

from __future__ import annotations

from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.agent_tool_catalog import agent_tool_definitions_for_allowed, catalog_entry
from app.orchestrator.evidence_signal_utils import is_day_trip_query
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.states.evidence_planning_and_tool_use_state import EvidencePlanningAndToolUseState
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_query import TravelAgentState
from app.tools import ToolRegistry


def test_baidu_route_catalog_has_day_trip_guidance():
    spec = catalog_entry("baidu_route_mcp")
    assert spec is not None
    joined = " ".join(spec.when_to_use)
    assert "一日游" in joined or "一天" in joined
    assert "origin" in spec.parameters


def test_agent_tool_definitions_filtered_to_allowed():
    defs = agent_tool_definitions_for_allowed(["baidu_route_mcp", "search_mcp", "unknown_tool"])
    names = {d["name"] for d in defs}
    assert names == {"baidu_route_mcp", "search_mcp", "unknown_tool"}
    route = next(d for d in defs if d["name"] == "baidu_route_mcp")
    assert route.get("when_to_use")


def test_s5_prompt_includes_agent_tool_definitions():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海一天够玩吗？")
    state.semantic_frame = SemanticFrame(
        raw_query="可可托海一天够玩吗？",
        normalized_request="可可托海一日游是否够用",
        task_family=TaskFamily.SUITABILITY,
        decision_type=DecisionType.WHETHER_TO_GO,
        entities=SemanticEntities(country="China", region="新疆", city="Altay", places=["可可托海风景区"]),
        information_needs=["opening_hours", "walking_intensity"],
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    state.travel_task = TravelTask(task_type=TravelTaskType.SINGLE_PLACE_SUITABILITY, country="China")
    s5 = EvidencePlanningAndToolUseState(llm_client=None, tools=ToolRegistry())
    wl = ToolWhitelistBuilder().build(state)
    ctx = s5._build_prompt_context(state, {}, wl)
    assert ctx.get("agent_tool_definitions")
    route_def = next((d for d in ctx["agent_tool_definitions"] if d["name"] == "baidu_route_mcp"), None)
    if "baidu_route_mcp" in wl.allowed_tool_names():
        assert route_def is not None
        assert route_def.get("when_to_use")


def test_agent_tool_definitions_include_task_class_when_resolved():
    from app.orchestrator.agent_tool_catalog import resolve_s5_task_class

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="戏马台附近有什么好吃的？")
    state.semantic_frame = SemanticFrame(
        raw_query="戏马台附近有什么好吃的？",
        task_family=TaskFamily.ADVISORY,
        entities=SemanticEntities(country="China", city="徐州", places=["戏马台"]),
        information_needs=["nearby_food"],
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    task_class = resolve_s5_task_class(state)
    assert task_class == "poi_recommendation"
    defs = agent_tool_definitions_for_allowed(
        ["dianping_nearby_crawler_mcp"],
        task_class=task_class,
    )
    assert defs[0]["s5_task_class"] == "poi_recommendation"
    assert any("美食" in line for line in defs[0].get("when_to_use") or [])


def test_ticket_price_lookup_resolves_specific_task_class():
    from app.orchestrator.agent_tool_catalog import resolve_s5_task_class

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="兵马俑门票多少钱？")
    state.semantic_frame = SemanticFrame(
        raw_query=state.raw_user_query,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="西安", places=["兵马俑"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    task_class = resolve_s5_task_class(state)
    assert task_class == "ticket_price_lookup"
    defs = agent_tool_definitions_for_allowed(["fact_lookup_agent"], task_class=task_class)
    assert defs[0]["s5_task_class"] == "ticket_price_lookup"
    assert "official_ticket_page_discovery" in defs[0]["parameters"]["lookup_phase"]


def test_route_tools_injected_for_day_trip_contract_queue():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海一天够玩吗？")
    state.semantic_frame = SemanticFrame(
        raw_query="可可托海一天够玩吗？",
        task_family=TaskFamily.SUITABILITY,
        decision_type=DecisionType.WHETHER_TO_GO,
        entities=SemanticEntities(country="China", region="新疆", places=["可可托海风景区"]),
    )
    state.response_contract = ResponseContractCompiler().compile(state.semantic_frame)
    wl = ToolWhitelistBuilder().build(state)
    allowed = set(wl.allowed_tool_names())
    controller = ActionModelController(llm_client=None)
    queue = controller._evidence_tool_queue(state, {"allowed_tools": [{"name": n} for n in allowed]})
    if "baidu_route_mcp" in allowed:
        assert "baidu_route_mcp" in queue
    assert is_day_trip_query(state.semantic_frame)
