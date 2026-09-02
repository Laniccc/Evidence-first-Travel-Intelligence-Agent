"""Shared claim contract at the composition/evidence boundary."""

from pydantic import BaseModel, Field


class AnswerClaim(BaseModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    claim_type: str = Field(min_length=1)
    hard_fact: bool
    evidence_ids: list[str] = Field(default_factory=list)
    attraction_id: str | None = None
    subtask_id: str | None = None
    conflict_disclosed: bool = False


__all__ = ["AnswerClaim"]
