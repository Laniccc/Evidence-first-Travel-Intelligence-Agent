"""S5 controlled A2A keyword search tests."""

import pytest

from app.agents.keyword_search_agent import KeywordSearchAgent
from app.agents.search_task_planner_agent import SearchTaskPlannerAgent
from app.evals.llm_test_helpers import StubLLMClient, duku_search_tasks_json
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.schemas.search_task import SearchTask
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.user_query import TravelAgentState


def _duku_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="新疆的独库公路每年几月份开放？",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", region="新疆", places=["独库公路"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit"],
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.response_contract = ResponseContractCompiler().compile(frame)
    return state


@pytest.mark.asyncio
async def test_search_task_planner_creates_keyword_tasks():
    llm = StubLLMClient(lambda _s, _u: duku_search_tasks_json())
    tasks = await SearchTaskPlannerAgent(llm).run(_duku_state())
    assert len(tasks) >= 3
    assert all(isinstance(t, SearchTask) for t in tasks)
    assert all(t.anchor_keywords for t in tasks)
    assert tasks[0].search_query == "独库公路什么时候开放"


def test_keyword_search_validates_anchors():
    task = SearchTask(
        task_id="t1",
        anchor_keywords=["独库公路", "开放"],
        search_query="独库公路什么时候开放",
    )
    KeywordSearchAgent.validate_task(task)

    bad = SearchTask(
        task_id="t2",
        anchor_keywords=["喀纳斯湖"],
        search_query="独库公路什么时候开放",
    )
    with pytest.raises(ValueError, match="anchor"):
        KeywordSearchAgent.validate_task(bad)


def test_evidence_guard_accepts_keyword_search_subagent():
    state = _duku_state()
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="keyword_search_agent",
        arguments={
            "task_id": "search-1",
            "anchor_keywords": ["独库公路", "开放"],
            "search_query": "独库公路几月通车",
            "information_need": "seasonal_operation_status",
            "preferred_tool": "search_mcp",
        },
    )
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, tool_whitelist=None)
