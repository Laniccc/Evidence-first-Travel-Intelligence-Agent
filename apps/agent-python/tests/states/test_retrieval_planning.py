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


@pytest.mark.asyncio
@pytest.mark.parametrize("reference,expected", [
    ("2026-09-06T01:00:00+08:00", "2026-09-05T17:00:00+00:00"),
    ("2026-09-06", "2026-09-05T16:00:00+00:00"),
    ("2026-09-06T01:00:00", "2026-09-05T17:00:00+00:00"),
])
async def test_explicit_time_and_constraints_survive_planning(reference, expected):
    ctx = state("fact_query", ["故宫博物院"], ["opening_hours"])
    req = ctx.artifacts["understand"]["normalized_request"]
    req.update(raw_query="原始问句", rewritten_query="重写问句",
               time_scope={"scope": "specific_date", "reference_date": reference},
               user_constraints={"party": ["老人"], "constraints": ["轮椅"]})
    result = await RetrievalPlanningHandler(attraction_resolver=IDS.get, clock=lambda: NOW).run(ctx)
    plan = RetrievalPlan.model_validate(result.output["retrieval_plans"][0])
    assert plan.as_of == datetime.fromisoformat(expected)
    assert plan.raw_query == "原始问句"
    assert plan.query_text == "重写问句"
    assert plan.user_constraints.constraints == ["轮椅"]
    assert plan.require_explicit_temporal_coverage
    assert "开放时间" in plan.lexical_query


@pytest.mark.asyncio
@pytest.mark.parametrize("date", ["2026-02-30", "下个周末", None])
async def test_invalid_or_missing_specific_date_clarifies(date):
    ctx = state("fact_query", ["故宫博物院"], ["opening_hours"])
    ctx.artifacts["understand"]["normalized_request"]["time_scope"] = {
        "scope": "specific_date", "reference_date": date}
    result = await RetrievalPlanningHandler(attraction_resolver=IDS.get, clock=lambda: NOW).run(ctx)
    assert result.next_state is AgentState.CLARIFICATION
    assert result.output["reason"] == "invalid_time_scope"


@pytest.mark.asyncio
async def test_rule_only_raw_date_is_not_lost_and_timezone_controls_cross_day():
    ctx = state("fact_query", ["故宫博物院"], ["opening_hours"])
    ctx.user_context = {"timezone": "Asia/Shanghai"}
    ctx.artifacts["understand"]["normalized_request"]["raw_query"] = "明天故宫几点开门"
    clock = datetime(2026, 9, 2, 17, tzinfo=UTC)  # Shanghai already Sep 3.
    result = await RetrievalPlanningHandler(attraction_resolver=IDS.get, clock=lambda: clock).run(ctx)
    assert RetrievalPlan.model_validate(result.output["retrieval_plans"][0]).as_of == datetime(
        2026, 9, 3, 16, tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["2026-02-30故宫几点开门", "9月6日故宫几点开门", "下周故宫几点开门", "大后天故宫几点开门"])
async def test_rule_ambiguous_dates_are_not_silently_replaced_by_today(query):
    ctx = state("fact_query", ["故宫博物院"], ["opening_hours"])
    ctx.artifacts["understand"]["normalized_request"]["raw_query"] = query
    result = await RetrievalPlanningHandler(attraction_resolver=IDS.get, clock=lambda: NOW).run(ctx)
    assert result.next_state is AgentState.CLARIFICATION


@pytest.mark.asyncio
async def test_top_k_is_operator_bounded_and_comparison_constraints_are_isolated():
    ctx = state("comparison", ["故宫博物院", "颐和园"], ["accessibility"])
    ctx.artifacts["understand"]["normalized_request"]["user_constraints"] = {"party": ["老人"]}
    result = await RetrievalPlanningHandler(attraction_resolver=IDS.get, clock=lambda: NOW, top_k=50).run(ctx)
    plans = [RetrievalPlan.model_validate(p) for p in result.output["retrieval_plans"]]
    assert all(p.top_k == 5 and p.user_constraints.party == ["老人"] for p in plans)
    assert "颐和园" not in plans[0].lexical_query
    assert "故宫博物院" not in plans[1].lexical_query
    assert len({p.subtask_id for p in plans}) == 2
    with pytest.raises(ValueError):
        RetrievalPlanningHandler(attraction_resolver=IDS.get, top_k=0)


@pytest.mark.asyncio
async def test_duplicate_catalog_identity_cannot_be_compared_to_itself():
    ctx = state("comparison", ["故宫", "故宫博物院"], ["accessibility"])
    result = await RetrievalPlanningHandler(attraction_resolver=lambda _: "same", clock=lambda: NOW).run(ctx)
    assert result.next_state is AgentState.CLARIFICATION


@pytest.mark.asyncio
@pytest.mark.parametrize("reference,zone", [
    ("2026-11-01T01:30:00", "America/New_York"),
    ("2026-03-08T02:30:00", "America/New_York"),
    ("2026-09-06", "Invalid/Timezone"),
])
async def test_ambiguous_dst_or_invalid_timezone_clarifies(reference, zone):
    ctx = state("fact_query", ["故宫博物院"], ["opening_hours"])
    ctx.user_context = {"timezone": zone}
    ctx.artifacts["understand"]["normalized_request"]["time_scope"] = {
        "scope": "specific_date", "reference_date": reference}
    result = await RetrievalPlanningHandler(attraction_resolver=IDS.get, clock=lambda: NOW).run(ctx)
    assert result.next_state is AgentState.CLARIFICATION
