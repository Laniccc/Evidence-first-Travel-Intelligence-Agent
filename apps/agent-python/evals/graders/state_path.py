"""Metrics for deterministic state-routing evaluation."""

from pydantic import BaseModel, Field


class StatePathCaseResult(BaseModel):
    case_id: str
    expected_terminal: str
    actual_terminal: str
    illegal_transition_count: int = Field(default=0, ge=0)


class StatePathMetrics(BaseModel):
    case_count: int = Field(ge=0)
    path_accuracy: float = Field(ge=0, le=1)
    illegal_transitions: int = Field(ge=0)


def grade_state_paths(cases: list[StatePathCaseResult]) -> StatePathMetrics:
    if not cases:
        return StatePathMetrics(case_count=0, path_accuracy=0.0, illegal_transitions=0)
    return StatePathMetrics(
        case_count=len(cases),
        path_accuracy=sum(
            case.expected_terminal == case.actual_terminal for case in cases
        )
        / len(cases),
        illegal_transitions=sum(case.illegal_transition_count for case in cases),
    )


__all__ = ["StatePathCaseResult", "StatePathMetrics", "grade_state_paths"]
