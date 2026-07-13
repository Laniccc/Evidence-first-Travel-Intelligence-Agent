from app.orchestration.non_lookup_task_chains import (
    NearbyCandidate as OrchestrationNearbyCandidate,
    TaskChainProfile as OrchestrationTaskChainProfile,
    TaskDebugTrace as OrchestrationTaskDebugTrace,
    build_minimal_clarification_question,
    build_non_lookup_task_draft,
    build_non_lookup_task_profile,
    ensure_non_lookup_task_contract,
    evaluate_non_lookup_task_evidence,
    is_non_lookup_task,
    prepare_non_lookup_task_compose_context,
    resolve_non_lookup_task_class,
)
from app.orchestration.travel_agent_state import TravelAgentState
from app.planning.intent_strategy_registry import resolve_intent_strategy
from app.planning.non_lookup_task_profile import (
    TaskChainProfile as PlanningTaskChainProfile,
    build_non_lookup_task_profile as build_planning_task_profile,
    is_non_lookup_task as planning_is_non_lookup_task,
    resolve_non_lookup_task_class as resolve_planning_task_class,
)
from app.evidence.non_lookup_task_evaluation import (
    NearbyCandidate as EvidenceNearbyCandidate,
    TaskDebugTrace as EvidenceTaskDebugTrace,
)
from app.composition.non_lookup_task_composition import (
    build_minimal_clarification_question as build_composition_clarification_question,
    build_non_lookup_task_draft as build_composition_task_draft,
    prepare_non_lookup_task_compose_context as build_composition_context,
)
from app.understanding.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    IntentProfile,
    PrimaryIntent,
)
from app.understanding.semantic_frame_model import SemanticFrame, TaskFamily


def _state_for(intent: PrimaryIntent) -> TravelAgentState:
    frame = SemanticFrame(raw_query=f"sample {intent.value}")
    frame.entities.places = ["Sample Place"]
    profile = IntentProfile(
        primary_intent=intent,
        evidence_sensitivity=EvidenceSensitivity.EVIDENCE_PREFERRED,
        answer_style=(
            AnswerStyle.CLARIFICATION
            if intent == PrimaryIntent.CLARIFICATION
            else AnswerStyle.ADVISORY
        ),
    )
    state = TravelAgentState(
        session_id="non-lookup-layer-test",
        query_id=intent.value,
        raw_user_query=frame.raw_query,
    )
    state.semantic_frame = frame
    state.intent_profile = profile
    state.intent_strategy = resolve_intent_strategy(profile)
    return state


def test_advisory_task_profile_and_contract_stay_coherent():
    state = _state_for(PrimaryIntent.ADVISORY)
    state.semantic_frame.task_family = TaskFamily.ADVISORY

    assert is_non_lookup_task(state)
    assert planning_is_non_lookup_task(state)
    assert resolve_non_lookup_task_class(state) == "advisory"
    assert resolve_planning_task_class(state) == "advisory"

    profile = build_non_lookup_task_profile(state)
    assert profile is not None
    assert profile.task_class == "advisory"
    assert profile.primary_claims == ["review_summary", "seasonality", "route_plan"]
    assert OrchestrationTaskChainProfile is PlanningTaskChainProfile
    assert OrchestrationTaskDebugTrace is EvidenceTaskDebugTrace
    assert OrchestrationNearbyCandidate is EvidenceNearbyCandidate
    assert profile.model_dump() == build_planning_task_profile(state).model_dump()

    contract = ensure_non_lookup_task_contract(state)
    assert state.response_contract is contract
    assert [claim.claim_type for claim in contract.claim_requirements[:3]] == profile.primary_claims
    assert build_non_lookup_task_draft(state).compose_mode == profile.compose_mode


def test_advisory_evaluation_and_composition_context_share_one_profile():
    state = _state_for(PrimaryIntent.ADVISORY)
    state.semantic_frame.task_family = TaskFamily.ADVISORY
    ensure_non_lookup_task_contract(state)

    report = evaluate_non_lookup_task_evidence(state)
    context = prepare_non_lookup_task_compose_context(state, {"target_label": "Sample Place"})

    assert state.evidence_decision_report is report
    assert context["non_lookup_task_profile"]["task_class"] == "advisory"
    assert context["task_composer_draft"]["compose_mode"] == context["compose_mode"]
    assert context["target_label"] == "Sample Place"


def test_clarification_contract_uses_the_same_user_question_in_s8_context():
    state = _state_for(PrimaryIntent.CLARIFICATION)
    state.semantic_frame.needs_clarification = True
    state.semantic_frame.missing_slots = ["city"]

    contract = ensure_non_lookup_task_contract(state)
    question = build_minimal_clarification_question(state)
    context = prepare_non_lookup_task_compose_context(state, {})

    assert contract.clarification_policy.should_ask is True
    assert contract.clarification_policy.question == question
    assert context["task_composer_draft"]["conclusion"] == question


def test_composition_owner_shapes_clarification_from_explicit_inputs():
    question = build_composition_clarification_question(
        related_poi=False,
        ambiguous_candidate_labels=["West Lake Hangzhou"],
        missing_slots=[],
    )
    draft = build_composition_task_draft(
        profile_payload={"task_class": "clarification", "compose_mode": "clarification"},
        target_label="West Lake",
        report=None,
        evidence=[],
        user_visible_limitations=[],
        clarification_question=question,
        nearby_candidates=[],
    )
    context = build_composition_context(
        compose_kwargs={},
        profile_payload={"task_class": "clarification", "compose_mode": "clarification"},
        trace_payload={"adoption_levels": {}},
        draft=draft,
        target_label="West Lake",
    )

    assert draft.conclusion == "Which place do you mean: West Lake Hangzhou?"
    assert context["task_composer_draft"]["conclusion"] == draft.conclusion
    assert context["non_lookup_task_profile"]["task_class"] == "clarification"
