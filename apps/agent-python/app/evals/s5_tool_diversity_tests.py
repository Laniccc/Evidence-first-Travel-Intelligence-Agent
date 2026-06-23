"""S5 tool diversity: priority tools + LLM review checkpoint after 2 searches."""

import json

import pytest

from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentActionType
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
)
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools import ToolRegistry


class _NoLLM:
    def _should_use_anthropic(self) -> bool:
        return False


class _ReviewLLM:
    def _should_use_anthropic(self) -> bool:
        return True

    async def complete(self, system: str, user: str, max_tokens: int = 900) -> str:
        return json.dumps(
            {
                "review_summary": "搜索无票价，改查官方页",
                "next_actions": [
                    {
                        "action_type": "call_tool",
                        "target": "official_page_reader_mcp",
                        "arguments": {},
                        "reason_summary": "读取官方页面",
                    },
                    {
                        "action_type": "call_tool",
                        "target": "baidu_place_detail_mcp",
                        "arguments": {},
                        "reason_summary": "补充 POI 详情",
                    },
                ],
                "finish_recommended": False,
            },
            ensure_ascii=False,
        )


def _ticket_frame() -> SemanticFrame:
    return SemanticFrame(
        raw_query="巴音布鲁克景区需要门票吗",
        normalized_request="巴音布鲁克景区门票",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["巴音布鲁克风景区"], region="Xinjiang"),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
        confidence=0.9,
    )


def _ticket_state() -> TravelAgentState:
    frame = _ticket_frame()
    contract = ResponseContractCompiler().compile(frame, None)
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
        response_contract=contract,
    )
    state.s5_domain_plan = S5DomainPlanner().plan(contract, frame)
    return state


def _whitelist_with_ticket_tools() -> ToolWhitelist:
    names = [
        "baidu_place_search_mcp",
        "baidu_place_detail_mcp",
        "official_page_reader_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "ticket_snapshot_store",
        "search_mcp",
    ]
    return ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[
            ToolDescriptor(name=n, description=n, capabilities=["ticket_price"], configured=True)
            for n in names
        ],
        blocked_tools=[],
        reason_by_tool={},
        policy_notes=[],
    )


def _ctx_with_searches(completed: int) -> dict:
    wl = _whitelist_with_ticket_tools()
    tasks = [
        {"task_id": f"t{i}", "search_query": f"巴音布鲁克 门票{i}", "anchor_keywords": ["巴音布鲁克"]}
        for i in range(1, 5)
    ]
    return {
        "tool_whitelist": wl,
        "allowed_tools": [{"name": t} for t in wl.allowed_tool_names()],
        "_search_task_planner_called": True,
        "_last_review_search_count": 0,
        "max_tool_calls": 10,
        "tool_call_count": 0,
        "tool_diversity_hints": ["ticket_price: try official_page_reader_mcp"],
    }, tasks, [f"t{i}" for i in range(1, completed + 1)]


@pytest.mark.asyncio
async def test_ticket_price_calls_priority_tool_before_search_planner():
    controller = ActionModelController(llm_client=_NoLLM())
    state = _ticket_state()
    ctx = {
        "tool_whitelist": _whitelist_with_ticket_tools(),
        "allowed_tools": [{"name": t} for t in _whitelist_with_ticket_tools().allowed_tool_names()],
        "max_tool_calls": 10,
    }
    action = await controller.next_action(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx, step=1
    )
    assert action.action_type == AgentActionType.CALL_TOOL
    assert action.target != "search_mcp"


@pytest.mark.asyncio
async def test_review_checkpoint_plans_two_tools_after_two_searches():
    controller = ActionModelController(llm_client=_ReviewLLM())
    state = _ticket_state()
    ctx, tasks, completed = _ctx_with_searches(2)
    state.structured_result = {"search_tasks": tasks, "completed_search_task_ids": completed}
    from app.schemas.tool_trace import ToolTrace

    state.tool_traces = [
        ToolTrace(tool_name="search_mcp", input={"query": "q1"}, status="ok"),
        ToolTrace(tool_name="search_mcp", input={"query": "q2"}, status="ok"),
    ]

    action = await controller.next_action(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx, step=5
    )
    assert action.action_type == AgentActionType.CALL_TOOL
    assert action.target == "official_page_reader_mcp"
    assert len(ctx.get("_tool_batch_queue") or []) == 1
    assert ctx["_tool_batch_queue"][0]["target"] == "baidu_place_detail_mcp"


@pytest.mark.asyncio
async def test_deterministic_review_fallback_without_llm():
    controller = ActionModelController(llm_client=_NoLLM())
    state = _ticket_state()
    ctx, tasks, completed = _ctx_with_searches(2)
    state.structured_result = {"search_tasks": tasks, "completed_search_task_ids": completed}
    from app.schemas.tool_trace import ToolTrace

    state.tool_traces = [
        ToolTrace(tool_name="search_mcp", input={"query": "q1"}, status="ok"),
        ToolTrace(tool_name="search_mcp", input={"query": "q2"}, status="ok"),
    ]

    action = await controller.next_action(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx, step=5
    )
    assert action.action_type == AgentActionType.CALL_TOOL
    assert action.target != "search_mcp"
    assert ctx.get("_tool_batch_queue")


def test_configured_ticket_providers_in_whitelist(monkeypatch):
    monkeypatch.setenv("TICKET_SNAPSHOT_STORE_ENABLED", "true")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "false")
    monkeypatch.setenv("TICKETLENS_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    state = _ticket_state()
    wl = ToolWhitelistBuilder(ToolRegistry()).build(state, {})
    assert "ticket_snapshot_store" in wl.allowed_tool_names()
    get_settings.cache_clear()
