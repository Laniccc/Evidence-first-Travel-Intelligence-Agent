import json
from pathlib import Path

from evals.graders.versioning import VersionCaseResult, grade_versioning


def test_expired_hit_fails_version_suite():
    metrics = grade_versioning(
        [VersionCaseResult(case_id="expired-1", status="expired", returned=True)]
    )

    assert metrics.expired_leakage_rate == 1.0
    assert metrics.stale_vector_rejection == 0.0


def test_non_active_versions_are_graded_by_status():
    metrics = grade_versioning(
        [
            VersionCaseResult(case_id="expired", status="expired", returned=False, rejected_by_post_filter=True),
            VersionCaseResult(case_id="superseded", status="superseded", returned=False, rejected_by_post_filter=True),
            VersionCaseResult(case_id="pending", status="pending", returned=False, rejected_by_post_filter=True),
            VersionCaseResult(case_id="rejected", status="rejected", returned=False, rejected_by_post_filter=True),
        ]
    )

    assert metrics.expired_leakage_rate == 0.0
    assert metrics.superseded_leakage_rate == 0.0
    assert metrics.non_active_leakage_rate == 0.0
    assert metrics.stale_vector_rejection == 1.0


def test_knowledge_fixture_has_the_approved_eval_shape():
    fixture = json.loads(
        (Path(__file__).parents[2] / "evals" / "fixtures" / "knowledge.json").read_text(
            encoding="utf-8"
        )
    )
    active_documents = fixture["active_documents"] + fixture["conflict_documents"]
    active_chunks = sum(len(row["facts"]) for row in active_documents)
    historical_chunks = sum(len(row["facts"]) for row in fixture["historical_documents"])
    review_chunks = sum(len(row["facts"]) for row in fixture["review_documents"])

    assert len({row["attraction_id"] for row in fixture["active_documents"]}) == 8
    assert 60 <= active_chunks <= 100
    assert historical_chunks == 12
    assert review_chunks == 8
    assert len(fixture["conflict_documents"]) == 6
