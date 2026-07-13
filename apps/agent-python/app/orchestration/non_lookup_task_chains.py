"""Thin S5/S7/S8 coordinator for non-lookup travel tasks."""

from __future__ import annotations

from typing import Iterable

from app.composition.final_answer_draft import FinalAnswerDraft
from app.composition.non_lookup_task_composition import (
    build_minimal_clarification_question as build_composition_clarification_question,
    build_non_lookup_task_draft as build_composition_task_draft,
    prepare_non_lookup_task_compose_context as build_composition_context,
)
from app.composition.response_contract import ClaimRequirement, ResponseContract
from app.evidence.evidence_decision_report import EvidenceDecisionReport
from app.evidence.evidence_evaluator import evaluate_evidence
from app.evidence.evidence_model import ClaimType, Evidence
from app.evidence.non_lookup_task_evaluation import (
    NearbyCandidate as EvidenceNearbyCandidate,
    TaskDebugTrace as EvidenceTaskDebugTrace,
    build_non_lookup_task_debug_trace as build_evidence_task_debug_trace,
    collect_nearby_candidates as collect_evidence_nearby_candidates,
    evaluate_non_lookup_task_evidence as evaluate_profile_evidence,
)
from app.orchestration.travel_agent_state import TravelAgentState
from app.planning.intent_strategy_registry import resolve_intent_strategy
from app.planning.non_lookup_task_profile import (
    NonLookupTaskClass,
    TaskChainProfile as PlanningTaskChainProfile,
    build_non_lookup_task_profile as build_planning_task_profile,
    claim_family_for_task,
    composition_style,
    empty_task_profile,
    is_non_lookup_task as planning_is_non_lookup_task,
    non_lookup_task_classes as planning_non_lookup_task_classes,
    profile_for_task,
    resolve_non_lookup_task_class as resolve_planning_task_class,
)
from app.understanding.semantic_frame_model import DecisionType, SemanticFrame, TaskFamily


_HARD_FACT_CLAIMS = {
    "ticket_price",
    "opening_hours",
    "temporary_closure",
    "reservation_policy",
    "seasonal_operation_status",
}
_LIVE_CLAIMS = {
    "current_weather",
    "weather",
    "weather_today",
    "traffic_status",
    "congestion_risk",
    "current_crowd",
    "current_crowd_estimate",
    "queue_time",
    "temporary_closure",
}

TaskChainProfile = PlanningTaskChainProfile
TaskDebugTrace = EvidenceTaskDebugTrace
NearbyCandidate = EvidenceNearbyCandidate

__all__ = [
    "FinalAnswerDraft",
    "NearbyCandidate",
    "NonLookupTaskClass",
    "ResponseContract",
    "TaskChainProfile",
    "TaskDebugTrace",
    "build_minimal_clarification_question",
    "build_non_lookup_task_debug_trace",
    "build_non_lookup_task_draft",
    "build_non_lookup_task_profile",
    "build_sample_trace_summaries",
    "collect_nearby_candidates",
    "ensure_non_lookup_task_contract",
    "evaluate_non_lookup_task_evidence",
    "is_non_lookup_task",
    "non_lookup_task_classes",
    "prepare_non_lookup_task_compose_context",
    "related_poi_not_disambiguation_same_scenic_area",
    "resolve_non_lookup_task_class",
    "should_use_non_lookup_task_context",
]


def non_lookup_task_classes() -> list[NonLookupTaskClass]:
    return planning_non_lookup_task_classes()


def is_non_lookup_task(state: TravelAgentState) -> bool:
    return planning_is_non_lookup_task(state)


def resolve_non_lookup_task_class(state: TravelAgentState) -> NonLookupTaskClass | None:
    return resolve_planning_task_class(state)


def build_non_lookup_task_profile(state: TravelAgentState) -> TaskChainProfile | None:
    return build_planning_task_profile(state)


def ensure_non_lookup_task_contract(state: TravelAgentState) -> ResponseContract:
    profile = build_non_lookup_task_profile(state)
    if not profile:
        if state.response_contract:
            return state.response_contract
        state.response_contract = ResponseContract()
        return state.response_contract

    existing = state.response_contract
    if existing and existing.claim_requirements:
        state.response_contract = _merge_contract_claims(existing, state)
        return state.response_contract

    contract = ResponseContract(
        user_goal_summary=state.raw_user_query,
        claim_requirements=_claim_requirements_for_task(profile, state),
    )
    contract.composition_policy.answer_style = composition_style(profile.task_class)
    if profile.task_class == "clarification":
        contract.clarification_policy.should_ask = True
        contract.clarification_policy.reason = "missing or ambiguous target"
        contract.clarification_policy.question = build_minimal_clarification_question(state)
    state.response_contract = contract
    return contract


def evaluate_non_lookup_task_evidence(state: TravelAgentState) -> EvidenceDecisionReport:
    """Coordinate S7 policy evaluation and its state-owned debug trace."""
    profile = build_non_lookup_task_profile(state)
    if not profile:
        report = evaluate_evidence(state, target_label=_target_label(state))
        state.evidence_decision_report = report
        return report

    ensure_non_lookup_task_contract(state)
    report = evaluate_profile_evidence(
        state,
        profile=profile,
        target_label=_target_label(state),
        clarification_question=build_minimal_clarification_question(state),
        related_poi=related_poi_not_disambiguation_same_scenic_area(state),
    )
    _attach_task_trace(state, build_non_lookup_task_debug_trace(state, report))
    return report


def prepare_non_lookup_task_compose_context(
    state: TravelAgentState,
    compose_kwargs: dict,
) -> dict:
    profile = build_non_lookup_task_profile(state)
    if not profile:
        return compose_kwargs
    report = state.evidence_decision_report or evaluate_non_lookup_task_evidence(state)
    trace = build_non_lookup_task_debug_trace(state, report)
    draft = build_non_lookup_task_draft(state, report)
    return build_composition_context(
        compose_kwargs=compose_kwargs,
        profile_payload=profile.model_dump(mode="json"),
        trace_payload=trace.model_dump(mode="json"),
        draft=draft,
        target_label=_target_label(state),
    )


def should_use_non_lookup_task_context(state: TravelAgentState) -> bool:
    task = resolve_non_lookup_task_class(state)
    return bool(task and task != "nearby")


def build_non_lookup_task_debug_trace(
    state: TravelAgentState,
    report: EvidenceDecisionReport | None = None,
) -> TaskDebugTrace:
    profile = build_non_lookup_task_profile(state) or empty_task_profile("advisory")
    return build_evidence_task_debug_trace(
        state,
        profile=profile,
        report=report or state.evidence_decision_report,
    )


def build_non_lookup_task_draft(
    state: TravelAgentState,
    report: EvidenceDecisionReport | None = None,
) -> FinalAnswerDraft:
    profile = build_non_lookup_task_profile(state) or empty_task_profile("advisory")
    return build_composition_task_draft(
        profile_payload=profile.model_dump(mode="json"),
        target_label=_target_label(state),
        report=report or state.evidence_decision_report,
        evidence=state.evidence,
        user_visible_limitations=state.user_visible_limitations,
        clarification_question=build_minimal_clarification_question(state),
        nearby_candidates=collect_nearby_candidates(state.evidence),
    )


def collect_nearby_candidates(evidence: Iterable) -> list[NearbyCandidate]:
    return collect_evidence_nearby_candidates(evidence)


def build_minimal_clarification_question(state: TravelAgentState) -> str:
    frame = state.semantic_frame
    labels: list[str] = []
    if frame and frame.place_ambiguity and frame.place_ambiguity.is_ambiguous:
        labels = [
            " ".join(part for part in (candidate.region, candidate.city, candidate.name) if part).strip()
            for candidate in frame.place_ambiguity.candidates[:3]
        ]
    return build_composition_clarification_question(
        related_poi=related_poi_not_disambiguation_same_scenic_area(state),
        ambiguous_candidate_labels=labels,
        missing_slots=frame.missing_slots if frame else [],
    )


def related_poi_not_disambiguation_same_scenic_area(state: TravelAgentState) -> bool:
    candidates = _candidate_dicts(state)
    if len(candidates) < 2:
        return False
    parents = {
        str(candidate.get("parent_place") or candidate.get("scenic_area") or candidate.get("parent") or "").strip()
        for candidate in candidates
    }
    parents.discard("")
    if len(parents) == 1:
        return True
    cities = {str(candidate.get("city") or "").strip() for candidate in candidates}
    cities.discard("")
    names = [str(candidate.get("name") or "").strip() for candidate in candidates]
    return len(cities) <= 1 and any(
        "gate" in name.lower() or "entrance" in name.lower() for name in names
    )


def build_sample_trace_summaries() -> dict[str, dict]:
    return {
        task: build_non_lookup_task_debug_trace(_sample_state(task)).model_dump(mode="json")
        for task in non_lookup_task_classes()
    }


def _claim_requirements_for_task(
    profile: TaskChainProfile,
    state: TravelAgentState,
) -> list[ClaimRequirement]:
    claims = list(dict.fromkeys([
        *profile.primary_claims,
        *_query_triggered_claims(state, profile.task_class),
    ]))
    requirements: list[ClaimRequirement] = []
    for claim in claims:
        hard = claim in _HARD_FACT_CLAIMS
        live = claim in _LIVE_CLAIMS or profile.task_class == "realtime_check"
        requirements.append(
            ClaimRequirement(
                claim_type=claim,
                claim_family=claim_family_for_task(profile.task_class, claim),
                priority=(
                    "required"
                    if profile.task_class
                    in {"planning", "comparison", "realtime_check", "clarification"}
                    else "important"
                ),
                requires_exact_fact=hard,
                requires_live_data=live,
                model_prior_allowed=(
                    profile.task_class == "advisory" and not hard and not live
                ),
                missing_behavior=(
                    "ask_clarification"
                    if profile.task_class == "clarification"
                    else "refuse_to_guess"
                    if hard or live
                    else "answer_with_limitation"
                ),
            )
        )
    return requirements


def _merge_contract_claims(
    contract: ResponseContract,
    state: TravelAgentState,
) -> ResponseContract:
    profile = build_non_lookup_task_profile(state)
    if not profile:
        return contract
    seen = {claim.claim_type for claim in contract.claim_requirements}
    additions = [
        claim
        for claim in _claim_requirements_for_task(profile, state)
        if claim.claim_type not in seen
    ]
    if not additions:
        return contract
    data = contract.model_dump()
    data["claim_requirements"] = [
        claim.model_dump() for claim in [*contract.claim_requirements, *additions]
    ]
    return ResponseContract.model_validate(data)


def _query_triggered_claims(
    state: TravelAgentState,
    task_class: NonLookupTaskClass,
) -> list[str]:
    text = (state.raw_user_query or "").lower()
    frame_needs = list(state.semantic_frame.information_needs or []) if state.semantic_frame else []
    claims = list(frame_needs)
    if any(token in text for token in ("ticket", "price", "fare", "门票", "票价")):
        claims.append("ticket_price")
    if any(token in text for token in ("open", "closed", "opening", "开放", "关门", "闭园")):
        claims.append("opening_hours")
    if task_class in {"advisory", "realtime_check"} and any(
        token in text
        for token in ("weather", "rain", "snow", "today", "tomorrow", "天气", "下雨", "今天", "明天")
    ):
        claims.append("current_weather" if task_class == "realtime_check" else "weather")
    if task_class == "planning":
        claims.extend(["route_plan", "duration", "distance"])
    if task_class == "nearby" and not any(claim.startswith("nearby_") for claim in claims):
        claims.append("nearby_poi")
    return claims


def _candidate_dicts(state: TravelAgentState) -> list[dict]:
    candidates: list[dict] = []
    if state.semantic_frame and state.semantic_frame.place_ambiguity:
        candidates.extend(
            candidate.model_dump()
            for candidate in state.semantic_frame.place_ambiguity.candidates
        )
    for candidate in (state.structured_result or {}).get("place_disambiguation_candidates") or []:
        if isinstance(candidate, dict):
            candidates.append(candidate)
    for evidence in state.evidence or []:
        if not isinstance(evidence, Evidence):
            continue
        for claim in evidence.claims:
            if claim.claim_type != ClaimType.PLACE_CANDIDATES:
                continue
            normalized = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
            bucket = normalized.get("candidates") or claim.value
            if isinstance(bucket, list):
                candidates.extend(candidate for candidate in bucket if isinstance(candidate, dict))
    return candidates


def _target_label(state: TravelAgentState) -> str:
    frame = state.semantic_frame
    if frame and frame.entities.places:
        return " vs ".join(frame.entities.places[:3])
    if frame and frame.entities.city:
        return frame.entities.city
    return state.raw_user_query[:30] or "destination"


def _attach_task_trace(state: TravelAgentState, trace: TaskDebugTrace) -> None:
    structured = dict(state.structured_result or {})
    structured["non_lookup_task_trace"] = trace.model_dump(mode="json")
    structured["non_lookup_task_class"] = trace.task_class
    state.structured_result = structured


def _sample_state(task_class: NonLookupTaskClass) -> TravelAgentState:
    frame = SemanticFrame(raw_query=f"sample {task_class}")
    frame.entities.places = ["Sample Place"]
    if task_class == "comparison":
        frame.task_family = TaskFamily.COMPARISON
        frame.entities.places = ["A", "B"]
    elif task_class == "planning":
        frame.task_family = TaskFamily.PLANNING
        frame.decision_type = DecisionType.ROUTE_PLAN
    elif task_class == "nearby":
        frame.decision_type = DecisionType.NEARBY_SEARCH
    elif task_class == "realtime_check":
        frame.requires_live_data = True
    elif task_class == "clarification":
        frame.needs_clarification = True
        frame.missing_slots = ["place"]
    else:
        frame.task_family = TaskFamily.ADVISORY
    state = TravelAgentState(
        session_id="sample",
        query_id=task_class,
        raw_user_query=frame.raw_query,
    )
    state.semantic_frame = frame
    state.intent_profile = profile_for_task(task_class)
    state.intent_strategy = resolve_intent_strategy(state.intent_profile)
    ensure_non_lookup_task_contract(state)
    return state
