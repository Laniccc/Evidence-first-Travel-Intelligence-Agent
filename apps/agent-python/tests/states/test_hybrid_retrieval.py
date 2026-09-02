import pytest

from app.evidence.retrieval.report import PostFilterRejection
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.hybrid_retrieval import HybridRetrievalHandler
from tests.fakes.failing_retrievers import (
    StaticRetriever,
    lexical_success_dense_timeout,
    plan,
    report,
)


def context(retrieval_plan=None):
    retrieval_plan = retrieval_plan or plan()
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="故宫开放时间",
        artifacts={
            "retrieval_plan": {
                "retrieval_plans": [retrieval_plan.model_dump(mode="json")]
            }
        },
    )


@pytest.mark.asyncio
async def test_dense_timeout_is_recovered_inside_hybrid_state():
    result = await HybridRetrievalHandler(
        retriever=lexical_success_dense_timeout()
    ).run(context())

    assert result.status == "recovered"
    assert result.next_state is AgentState.EVIDENCE_EVALUATE
    assert result.recovery.strategy == "lexical_only"
    assert result.output["retrieval_reports"][0]["dense_attempt"]["failure_code"] == "timeout"


@pytest.mark.asyncio
async def test_two_empty_channels_go_to_bounded_gap_fill_with_report():
    result = await HybridRetrievalHandler(
        retriever=StaticRetriever([report(degradation="no_results")])
    ).run(context())

    assert result.next_state is AgentState.LIVE_GAP_FILL
    assert result.output["retrieval_reports"][0]["degradation"] == "no_results"


@pytest.mark.asyncio
async def test_stale_point_rejection_remains_in_state_artifact():
    stale = PostFilterRejection(chunk_id="stale", reason="hash_mismatch", channel="dense")
    result = await HybridRetrievalHandler(
        retriever=StaticRetriever([report(degradation="no_results", rejections=[stale])])
    ).run(context())

    assert result.output["retrieval_reports"][0]["post_filter_rejections"] == [
        {"chunk_id": "stale", "reason": "hash_mismatch", "channel": "dense"}
    ]
