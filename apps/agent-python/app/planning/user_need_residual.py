"""S2-derived user need context for S5/S7/S8 — excludes user-stated facts."""

from __future__ import annotations

from typing import Any

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
    time_scope: str = "unknown"
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


def build_user_need_residual(state: Any) -> UserNeedResidual:
    """Build S2/S3-derived user needs without promoting user text to facts."""
    norm = state.normalized_request
    frame = state.semantic_frame
    contract = state.response_contract

    information_needs: list[ResidualInformationNeed] = []
    if norm and norm.information_needs:
        information_needs = [
            ResidualInformationNeed(
                need_type=need.need_type,
                priority=need.priority,
                reason=need.reason,
            )
            for need in norm.information_needs
        ]
    elif frame and frame.information_needs:
        information_needs = [
            ResidualInformationNeed(need_type=need_type, priority="medium")
            for need_type in frame.information_needs
        ]

    constraints = ResidualUserConstraints()
    if norm and norm.user_constraints:
        user_constraints = norm.user_constraints
        constraints = ResidualUserConstraints(
            party=list(user_constraints.party),
            pace=user_constraints.pace,
            budget=user_constraints.budget,
            preferences=list(user_constraints.preferences),
            constraints=list(user_constraints.constraints),
        )
    elif frame and frame.user_constraints:
        constraints = ResidualUserConstraints(constraints=list(frame.user_constraints))

    answer_policy = ResidualAnswerPolicy()
    if norm and norm.answer_policy:
        policy = norm.answer_policy
        answer_policy = ResidualAnswerPolicy(
            requires_live_data=policy.requires_live_data,
            requires_exact_fact=policy.requires_exact_fact,
            can_answer_with_model_prior=policy.can_answer_with_model_prior,
            must_use_official_source=policy.must_use_official_source,
            allow_partial_answer=policy.allow_partial_answer,
            should_add_limitations=policy.should_add_limitations,
        )
    elif frame:
        answer_policy = ResidualAnswerPolicy(
            requires_live_data=frame.requires_live_data,
            requires_exact_fact=frame.requires_exact_fact,
            can_answer_with_model_prior=frame.can_answer_with_model_prior,
        )

    claim_requirements: list[ResidualClaimRequirement] = []
    if contract:
        claim_requirements = [
            ResidualClaimRequirement(
                claim_type=claim.claim_type,
                priority=claim.priority,
                model_prior_allowed=claim.model_prior_allowed,
            )
            for claim in contract.claim_requirements
        ]

    key_concerns = []
    if frame and frame.key_concerns:
        key_concerns = list(frame.key_concerns)
    elif state.query_understanding and state.query_understanding.key_concerns:
        key_concerns = list(state.query_understanding.key_concerns)

    time_scope = "unknown"
    if norm and norm.time_scope:
        time_scope = norm.time_scope.scope
    elif frame and frame.time_scope:
        time_scope = frame.time_scope.value

    return UserNeedResidual(
        intent_summary=(norm.intent_summary if norm else "") or (frame.normalized_request if frame else ""),
        query_scope=(norm.query_scope if norm else None) or (frame.query_scope.value if frame else "unknown"),
        task_family=(norm.task_family if norm else None) or (frame.task_family.value if frame else "unknown"),
        decision_type=(norm.decision_type if norm else None) or (frame.decision_type.value if frame else "unknown"),
        time_scope=time_scope,
        information_needs=information_needs,
        user_constraints=constraints,
        answer_policy=answer_policy,
        key_concerns=key_concerns,
        missing_slots=list(frame.missing_slots) if frame else [],
        claim_requirements=claim_requirements,
        requires_exact_fact=bool(frame.requires_exact_fact) if frame else answer_policy.requires_exact_fact,
        requires_live_data=bool(frame.requires_live_data) if frame else answer_policy.requires_live_data,
    )


def attach_user_need_residual(state: Any) -> Any:
    state.user_need_residual = build_user_need_residual(state)
    return state
