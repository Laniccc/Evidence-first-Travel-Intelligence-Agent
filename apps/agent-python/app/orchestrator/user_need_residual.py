"""Build isolated user-need residual from S2/S3 state for S7/S8."""

from __future__ import annotations

from app.schemas.user_need_residual import (
    ResidualAnswerPolicy,
    ResidualClaimRequirement,
    ResidualInformationNeed,
    ResidualUserConstraints,
    UserNeedResidual,
)
from app.schemas.user_query import TravelAgentState


def build_user_need_residual(state: TravelAgentState) -> UserNeedResidual:
    norm = state.normalized_request
    frame = state.semantic_frame
    contract = state.response_contract

    information_needs: list[ResidualInformationNeed] = []
    if norm and norm.information_needs:
        for need in norm.information_needs:
            information_needs.append(
                ResidualInformationNeed(
                    need_type=need.need_type,
                    priority=need.priority,
                    reason=need.reason,
                )
            )
    elif frame and frame.information_needs:
        for need_type in frame.information_needs:
            information_needs.append(ResidualInformationNeed(need_type=need_type, priority="medium"))

    constraints = ResidualUserConstraints()
    if norm and norm.user_constraints:
        uc = norm.user_constraints
        constraints = ResidualUserConstraints(
            party=list(uc.party),
            pace=uc.pace,
            budget=uc.budget,
            preferences=list(uc.preferences),
            constraints=list(uc.constraints),
        )
    elif frame and frame.user_constraints:
        constraints = ResidualUserConstraints(constraints=list(frame.user_constraints))

    answer_policy = ResidualAnswerPolicy()
    if norm and norm.answer_policy:
        ap = norm.answer_policy
        answer_policy = ResidualAnswerPolicy(
            requires_live_data=ap.requires_live_data,
            requires_exact_fact=ap.requires_exact_fact,
            can_answer_with_model_prior=ap.can_answer_with_model_prior,
            must_use_official_source=ap.must_use_official_source,
            allow_partial_answer=ap.allow_partial_answer,
            should_add_limitations=ap.should_add_limitations,
        )
    elif frame:
        answer_policy = ResidualAnswerPolicy(
            requires_live_data=frame.requires_live_data,
            requires_exact_fact=frame.requires_exact_fact,
            can_answer_with_model_prior=frame.can_answer_with_model_prior,
        )

    claim_requirements: list[ResidualClaimRequirement] = []
    if contract:
        for claim in contract.claim_requirements:
            claim_requirements.append(
                ResidualClaimRequirement(
                    claim_type=claim.claim_type,
                    priority=claim.priority,
                    model_prior_allowed=claim.model_prior_allowed,
                )
            )

    key_concerns: list[str] = []
    if frame and frame.key_concerns:
        key_concerns = list(frame.key_concerns)
    elif state.query_understanding and state.query_understanding.key_concerns:
        key_concerns = list(state.query_understanding.key_concerns)

    return UserNeedResidual(
        intent_summary=(norm.intent_summary if norm else "") or (frame.normalized_request if frame else ""),
        query_scope=(norm.query_scope if norm else None) or (frame.query_scope.value if frame else "unknown"),
        task_family=(norm.task_family if norm else None) or (frame.task_family.value if frame else "unknown"),
        decision_type=(norm.decision_type if norm else None) or (frame.decision_type.value if frame else "unknown"),
        information_needs=information_needs,
        user_constraints=constraints,
        answer_policy=answer_policy,
        key_concerns=key_concerns,
        missing_slots=list(frame.missing_slots) if frame else [],
        claim_requirements=claim_requirements,
        requires_exact_fact=bool(frame.requires_exact_fact) if frame else answer_policy.requires_exact_fact,
        requires_live_data=bool(frame.requires_live_data) if frame else answer_policy.requires_live_data,
    )


def attach_user_need_residual(state: TravelAgentState) -> TravelAgentState:
    state.user_need_residual = build_user_need_residual(state)
    return state
