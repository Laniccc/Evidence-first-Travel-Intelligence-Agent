"""Untrusted model proposals; catalog IDs and retrieval budgets belong to code."""

from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.contracts.fact_type import FactType
from app.understanding.normalized_user_request import NormalizedUserRequest

Text = Annotated[str, Field(min_length=1, max_length=500)]


class StrictProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskEntity(StrictProposal):
    name: Text


class TaskConstraints(StrictProposal):
    party: list[Text] = Field(default_factory=list, max_length=8)
    pace: Text | None = None
    budget: Text | None = None
    preferences: list[Text] = Field(default_factory=list, max_length=12)
    constraints: list[Text] = Field(default_factory=list, max_length=12)


class TaskRequest(StrictProposal):
    task_type: Literal["fact_query", "suitability", "comparison", "clarification"]
    rewritten_query: str = Field(min_length=1, max_length=4000)
    entities: list[TaskEntity] = Field(max_length=2)
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    fact_types: list[FactType] = Field(default_factory=list, max_length=7)
    requested_as_of: AwareDatetime | None = None
    clarification_question: Text | None = None

    @model_validator(mode="after")
    def check_task_shape(self) -> Self:
        if self.task_type == "clarification":
            if not self.clarification_question:
                raise ValueError("clarification requires a question")
        else:
            expected = 2 if self.task_type == "comparison" else 1
            if len(self.entities) != expected:
                raise ValueError("task entity count mismatch")
            if len({e.name.casefold() for e in self.entities}) != expected:
                raise ValueError("comparison requires distinct entities")
            if self.clarification_question is not None:
                raise ValueError("question only permitted for clarification")
        return self


def to_normalized_request(task: TaskRequest, *, raw_query: str) -> NormalizedUserRequest:
    family = {"fact_query": "fact_lookup", "clarification": "unknown"}.get(
        task.task_type, task.task_type
    )
    return NormalizedUserRequest.model_validate({
        "raw_query": raw_query,
        "rewritten_query": task.rewritten_query,
        "query_scope": "place",
        "task_family": family,
        "decision_type": "how_to_choose" if task.task_type == "comparison" else "fact_lookup",
        "entities": [{"text": e.name, "normalized_name": e.name,
                      "entity_type": "attraction", "source": "llm_understanding",
                      "needs_verification": True} for e in task.entities],
        "time_scope": {
            "scope": "specific_date" if task.requested_as_of else "current",
            "reference_date": task.requested_as_of.isoformat() if task.requested_as_of else None,
        },
        "user_constraints": task.constraints.model_dump(),
        "information_needs": [{"need_type": f.value, "priority": "required"} for f in task.fact_types],
        "answer_policy": {"requires_exact_fact": True, "can_answer_with_model_prior": False},
        "needs_clarification": task.task_type == "clarification",
        "clarification_question": task.clarification_question,
    })
