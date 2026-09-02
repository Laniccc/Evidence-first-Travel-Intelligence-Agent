from datetime import UTC, datetime

import pytest

from app.evidence.knowledge.models import FactType
from app.evidence.retrieval.contracts import RetrievalPlan
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.retrieval_planning import RetrievalPlanningHandler
from app.understanding.normalized_user_request import (
    InformationNeedDraft,
    NormalizedEntity,
    NormalizedUserRequest,
)


NOW = datetime(2026, 9, 2, tzinfo=UTC)
IDS = {"故宫博物院": "forbidden-city", "颐和园": "summer-palace"}


def state(task_family: str, names: list[str], needs: list[str]) -> StateContext:
    normalized_family = "fact_lookup" if task_family == "fact_query" else task_family
    request = NormalizedUserRequest(
        raw_query="query",
        rewritten_query="query",
        query_scope="place",
        task_family=normalized_family,
        entities=[
            NormalizedEntity(text=name, normalized_name=name, entity_type="attraction")
            for name in names
        ],
        information_needs=[InformationNeedDraft(need_type=need) for need in needs],
    )
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="query",
        artifacts={
            "understand": {"normalized_request": request.model_dump(mode="json")},
            "route": {"task_type": task_family},
        },
    )


@pytest.mark.asyncio
async def test_retrieval_plan_uses_fact_type_whitelist_and_one_attraction():
    handler = RetrievalPlanningHandler(attraction_resolver=IDS.__getitem__, clock=lambda: NOW)

    result = await handler.run(state("fact_query", ["故宫博物院"], ["opening_hours", "made_up"]))

    assert result.next_state is AgentState.HYBRID_RETRIEVE
    plans = [RetrievalPlan.model_validate(item) for item in result.output["retrieval_plans"]]
    assert len(plans) == 1
    assert plans[0].attraction_ids == ["forbidden-city"]
    assert plans[0].fact_types == [FactType.OPENING_HOURS]
    assert plans[0].as_of == NOW


@pytest.mark.asyncio
async def test_comparison_creates_isolated_subtask_for_each_attraction():
    handler = RetrievalPlanningHandler(attraction_resolver=IDS.__getitem__, clock=lambda: NOW)

    result = await handler.run(
        state("comparison", ["故宫博物院", "颐和园"], ["accessibility"])
    )

    plans = [RetrievalPlan.model_validate(item) for item in result.output["retrieval_plans"]]
    assert [plan.attraction_ids for plan in plans] == [["forbidden-city"], ["summer-palace"]]
    assert len({plan.subtask_id for plan in plans}) == 2
    assert all(plan.task_type == "comparison" for plan in plans)


@pytest.mark.asyncio
async def test_retrieval_plan_clarifies_when_attraction_cannot_be_resolved():
    handler = RetrievalPlanningHandler(attraction_resolver=lambda _: None, clock=lambda: NOW)

    result = await handler.run(state("fact_query", ["未知景点"], ["opening_hours"]))

    assert result.next_state is AgentState.CLARIFICATION
    assert result.output["reason"] == "unresolved_attraction"
