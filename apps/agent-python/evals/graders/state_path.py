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


class ConversationCaseResult(BaseModel):
    case_id: str
    expected_terminal: str
    actual_terminal: str
    expected_attractions: list[str] = Field(default_factory=list)
    actual_attractions: list[str] = Field(default_factory=list)
    plan_isolation_ok: bool = True


class ConversationMetrics(BaseModel):
    case_count: int = Field(ge=0)
    task_accuracy: float = Field(ge=0, le=1)
    entity_accuracy: float = Field(ge=0, le=1)
    plan_isolation_accuracy: float = Field(ge=0, le=1)


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


def grade_conversations(cases: list[ConversationCaseResult]) -> ConversationMetrics:
    if not cases:
        return ConversationMetrics(
            case_count=0,
            task_accuracy=0,
            entity_accuracy=0,
            plan_isolation_accuracy=0,
        )
    count = len(cases)
    return ConversationMetrics(
        case_count=count,
        task_accuracy=sum(item.expected_terminal == item.actual_terminal for item in cases) / count,
        entity_accuracy=sum(item.expected_attractions == item.actual_attractions for item in cases) / count,
        plan_isolation_accuracy=sum(item.plan_isolation_ok for item in cases) / count,
    )


__all__ = [
    "ConversationCaseResult",
    "ConversationMetrics",
    "StatePathCaseResult",
    "StatePathMetrics",
    "grade_conversations",
    "grade_state_paths",
]
