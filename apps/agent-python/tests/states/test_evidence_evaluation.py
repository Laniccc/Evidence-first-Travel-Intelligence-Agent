import pytest

from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.evidence_evaluation import EvidenceEvaluationHandler
from tests.fakes.failing_retrievers import chunk, plan, report


def context(reports, *, gap_attempted=False):
    artifacts = {
        "retrieval_plan": {
            "retrieval_plans": [item.retrieval_plan.model_dump(mode="json") for item in reports]
        },
        "hybrid_retrieve": {
            "retrieval_reports": [item.model_dump(mode="json") for item in reports]
        },
    }
    if gap_attempted:
        artifacts["live_gap_fill"] = {
            "logical_gap_task_count": 1,
            "attempts": [],
            "transient_evidence": [],
        }
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="query",
        artifacts=artifacts,
    )


@pytest.mark.asyncio
async def test_conflicting_sources_are_both_retained_with_reason():
    retrieval_report = report(
        hits=[
            chunk("official", "故宫八点三十分开放", authority=1.0),
            chunk("structured", "故宫九点开放", authority=0.8),
        ]
    )

    result = await EvidenceEvaluationHandler().run(context([retrieval_report]))

    decision = result.output["claim_decisions"][0]
    assert decision["adoption"] == "adopt_with_limitation"
    assert set(decision["adopted_evidence_ids"]) == {"official", "structured"}
    assert "conflict" in decision["reason"]
    assert result.next_state is AgentState.COMPOSE


@pytest.mark.asyncio
async def test_missing_hard_fact_requests_one_gap_fill():
    result = await EvidenceEvaluationHandler().run(
        context([report(degradation="no_results")])
    )

    assert result.next_state is AgentState.LIVE_GAP_FILL
    assert result.output["coverage_report"]["all_required_covered"] is False


@pytest.mark.asyncio
async def test_missing_hard_fact_abstains_after_gap_budget_is_used():
    result = await EvidenceEvaluationHandler().run(
        context([report(degradation="no_results")], gap_attempted=True)
    )

    assert result.next_state is AgentState.SAFE_FAILURE
    assert result.output["abstain"] is True


@pytest.mark.asyncio
async def test_comparison_exposes_only_common_fact_dimensions():
    first_plan = plan(
        subtask_id="left", attraction_id="forbidden-city", task_type="comparison"
    )
    second_plan = plan(
        subtask_id="right", attraction_id="summer-palace", task_type="comparison"
    )
    first = report(first_plan, hits=[chunk("left-hours", "故宫八点开放")])
    second = report(
        second_plan,
        hits=[chunk("right-hours", "颐和园六点开放", attraction_id="summer-palace")],
    )

    result = await EvidenceEvaluationHandler().run(context([first, second]))

    assert result.output["common_fact_types"] == ["opening_hours"]
    assert set(result.output["comparison_artifacts"]) == {
        "comparison:left",
        "comparison:right",
    }
