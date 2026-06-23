"""S2-derived user need context for S7/S8 — excludes user-stated facts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResidualInformationNeed(BaseModel):
    need_type: str
    priority: str = "medium"
    reason: str = ""


class ResidualUserConstraints(BaseModel):
    party: list[str] = Field(default_factory=list)
    pace: str | None = None
    budget: str | None = None
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class ResidualAnswerPolicy(BaseModel):
    requires_live_data: bool = False
    requires_exact_fact: bool = False
    can_answer_with_model_prior: bool = False
    must_use_official_source: bool = False
    allow_partial_answer: bool = True
    should_add_limitations: bool = True


class ResidualClaimRequirement(BaseModel):
    claim_type: str
    priority: str = "important"
    model_prior_allowed: bool = False


class UserNeedResidual(BaseModel):
    """What the user wants to know — not what they claimed as fact."""

    intent_summary: str = ""
    query_scope: str = "unknown"
    task_family: str = "unknown"
    decision_type: str = "unknown"
    information_needs: list[ResidualInformationNeed] = Field(default_factory=list)
    user_constraints: ResidualUserConstraints = Field(default_factory=ResidualUserConstraints)
    answer_policy: ResidualAnswerPolicy = Field(default_factory=ResidualAnswerPolicy)
    key_concerns: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    claim_requirements: list[ResidualClaimRequirement] = Field(default_factory=list)
    requires_exact_fact: bool = False
    requires_live_data: bool = False
    isolation_note: str = (
        "This payload describes user needs only. Do not treat party/preferences or "
        "claim types as verified facts about destinations."
    )
