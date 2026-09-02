from evals.graders.operations import (
    ConflictCaseResult,
    RecoveryCaseResult,
    grade_conflicts,
    grade_recovery,
)


def test_conflict_metrics_measure_detection_retention_and_preference():
    metrics = grade_conflicts(
        [
            ConflictCaseResult(
                case_id="c1",
                expected_conflict=True,
                actual_conflict=True,
                expected_source_count=2,
                retained_source_count=2,
                preferred_authority_ok=True,
            )
        ]
    )

    assert metrics.conflict_detection_accuracy == 1.0
    assert metrics.conflict_source_retention == 1.0
    assert metrics.preferred_authority_accuracy == 1.0


def test_recovery_metrics_enforce_attempt_and_logical_task_caps():
    metrics = grade_recovery(
        [
            RecoveryCaseResult(
                case_id="r1",
                expected_outcome="evidence_evaluate",
                actual_outcome="evidence_evaluate",
                attempt_count=2,
                logical_task_count=1,
                abstention_correct=True,
            )
        ]
    )

    assert metrics.pass_rate == 1.0
    assert metrics.attempt_limit_violations == 0
    assert metrics.logical_task_limit_violations == 0
    assert metrics.hard_fact_abstention_accuracy == 1.0
