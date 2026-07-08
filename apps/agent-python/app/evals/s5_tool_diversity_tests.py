"""S5 orchestrator: functional sub-agents replace direct MCP + search_task_planner loop."""

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

    async def complete(self, system: str, user: str, max_tokens: int = 900, **kwargs) -> str:
        return json.dumps(
            {
                "action_type": "call_subagent",
                "target": "fact_search_agent",
                "arguments": {
                    "lookup_intent": "查巴音布鲁克官方门票",
                    "search_query": "巴音布鲁克 官网 门票",
                    "anchor_keywords": ["巴音布鲁克"],
                    "claim_target": "ticket_price",
                    "information_need": "ticket_price",
                },
                "reason_summary": "搜索无票价，委派 fact_search 查官方",
                "confidence": 0.85,
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


@pytest.mark.asyncio
async def test_ticket_price_orchestrator_delegates_entity_resolution_first():
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
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "entity_resolution_agent"


@pytest.mark.asyncio
async def test_orchestrator_llm_delegates_fact_search_after_entity():
    controller = ActionModelController(llm_client=_ReviewLLM())
    state = _ticket_state()
    state.structured_result = {
        "subagent_results": [
            {
                "subagent": "entity_resolution_agent",
                "evidence_count": 1,
                "resolution_status": "resolved",
            }
        ],
    }
    ctx = {
        "tool_whitelist": _whitelist_with_ticket_tools(),
        "allowed_tools": [{"name": t} for t in _whitelist_with_ticket_tools().allowed_tool_names()],
        "max_tool_calls": 10,
    }
    action = await controller.next_action(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx, step=3
    )
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "fact_search_agent"


@pytest.mark.asyncio
async def test_orchestrator_fallback_fact_search_after_entity_done():
    controller = ActionModelController(llm_client=_NoLLM())
    state = _ticket_state()
    state.semantic_frame.entities.city = "巴音郭楞"
    state.structured_result = {
        "subagent_results": [
            {"subagent": "entity_resolution_agent", "evidence_count": 1},
        ],
    }
    ctx = {
        "tool_whitelist": _whitelist_with_ticket_tools(),
        "allowed_tools": [{"name": t} for t in _whitelist_with_ticket_tools().allowed_tool_names()],
        "max_tool_calls": 10,
    }
    action = await controller.next_action(
        state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, ctx, step=3
    )
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "fact_search_agent"


def test_s5_max_steps_is_30():
    assert EVIDENCE_PLANNING_AND_TOOL_USE_POLICY.max_steps == 30


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
