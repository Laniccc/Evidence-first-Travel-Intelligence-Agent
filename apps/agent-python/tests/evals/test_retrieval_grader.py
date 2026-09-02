import pytest

from evals.graders.retrieval import RetrievalCaseResult, grade_retrieval


def test_retrieval_metrics_are_computed_from_ranked_chunk_ids():
    metrics = grade_retrieval(
        [
            RetrievalCaseResult(
                case_id="case-1",
                expected_chunk_ids=["c2"],
                ranked_chunk_ids=["c1", "c2", "c3"],
                metadata_filter_ok=True,
                provenance_complete=True,
            )
        ]
    )

    assert metrics.recall_at_3 == 1.0
    assert metrics.mrr == 0.5
    assert metrics.ndcg_at_5 == pytest.approx(1 / 1.5849625007)
    assert metrics.metadata_filter_accuracy == 1.0
    assert metrics.provenance_completeness == 1.0


def test_retrieval_grader_averages_failures_instead_of_hiding_them():
    metrics = grade_retrieval(
        [
            RetrievalCaseResult(
                case_id="hit",
                expected_chunk_ids=["a"],
                ranked_chunk_ids=["a"],
            ),
            RetrievalCaseResult(
                case_id="miss",
                expected_chunk_ids=["b"],
                ranked_chunk_ids=[],
                metadata_filter_ok=False,
                provenance_complete=False,
            ),
        ]
    )

    assert metrics.recall_at_3 == 0.5
    assert metrics.mrr == 0.5
    assert metrics.metadata_filter_accuracy == 0.5
