"""Operational correctness metrics for conflicts and bounded recovery."""

from pydantic import BaseModel, Field


class ConflictCaseResult(BaseModel):
    case_id: str
    expected_conflict: bool
    actual_conflict: bool
    expected_source_count: int = Field(ge=0)
    retained_source_count: int = Field(ge=0)
    preferred_authority_ok: bool


class ConflictMetrics(BaseModel):
    case_count: int
    conflict_detection_accuracy: float
    conflict_source_retention: float
    preferred_authority_accuracy: float


class RecoveryCaseResult(BaseModel):
    case_id: str
    expected_outcome: str
    actual_outcome: str
    attempt_count: int = Field(ge=0)
    logical_task_count: int = Field(ge=0)
    abstention_correct: bool = True


class RecoveryMetrics(BaseModel):
    case_count: int
    pass_rate: float
    attempt_limit_violations: int
    logical_task_limit_violations: int
    hard_fact_abstention_accuracy: float


class ConsistencyMetrics(BaseModel):
    index_rebuild_consistency: float = Field(ge=0, le=1)
    replay_consistency: float = Field(ge=0, le=1)


def grade_conflicts(cases: list[ConflictCaseResult]) -> ConflictMetrics:
    total = len(cases)
    if not total:
        return ConflictMetrics(
            case_count=0,
            conflict_detection_accuracy=0,
            conflict_source_retention=0,
            preferred_authority_accuracy=0,
        )
    return ConflictMetrics(
        case_count=total,
        conflict_detection_accuracy=sum(
            item.expected_conflict == item.actual_conflict for item in cases
        ) / total,
        conflict_source_retention=sum(
            item.retained_source_count >= item.expected_source_count for item in cases
        ) / total,
        preferred_authority_accuracy=sum(item.preferred_authority_ok for item in cases)
        / total,
    )


def grade_recovery(cases: list[RecoveryCaseResult]) -> RecoveryMetrics:
    total = len(cases)
    if not total:
        return RecoveryMetrics(
            case_count=0,
            pass_rate=0,
            attempt_limit_violations=0,
            logical_task_limit_violations=0,
            hard_fact_abstention_accuracy=0,
        )
    return RecoveryMetrics(
        case_count=total,
        pass_rate=sum(item.expected_outcome == item.actual_outcome for item in cases)
        / total,
        attempt_limit_violations=sum(item.attempt_count > 2 for item in cases),
        logical_task_limit_violations=sum(item.logical_task_count > 1 for item in cases),
        hard_fact_abstention_accuracy=sum(item.abstention_correct for item in cases)
        / total,
    )


__all__ = [
    "ConflictCaseResult",
    "ConflictMetrics",
    "ConsistencyMetrics",
    "RecoveryCaseResult",
    "RecoveryMetrics",
    "grade_conflicts",
    "grade_recovery",
]
