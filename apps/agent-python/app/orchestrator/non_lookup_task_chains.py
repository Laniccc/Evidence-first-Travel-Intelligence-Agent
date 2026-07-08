"""Task-class state chains for non-lookup intents.

This module is intentionally thin: it turns the existing IntentStrategy,
S5DomainPlan, EvidenceEvaluator, and FinalAnswerDraft primitives into a
task-specific S5/S7/S8 contract that tests and debug tooling can rely on.
It does not hardcode destination facts; every adopted user-facing value must
come from Evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Literal

from pydantic import BaseModel, Field

from app.schemas.user_query import TravelAgentState
from app.orchestrator.evidence_evaluator import evaluate_evidence
from app.orchestrator.intent_strategy_registry import IntentStrategy, resolve_intent_strategy
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.schemas.evidence import ClaimType, DataFreshness, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.s5_information_domain import InformationDomain, ProviderGroup
from app.schemas.semantic_frame import DecisionType, SemanticFrame, TaskFamily
from app.schemas.tool_trace import ToolTrace


NonLookupTaskClass = Literal[
    "advisory",
    "review_check",
    "planning",
    "comparison",
    "nearby",
    "realtime_check",
    "clarification",
]

_NON_LOOKUP_INTENTS: frozenset[PrimaryIntent] = frozenset(
    {
        PrimaryIntent.ADVISORY,
        PrimaryIntent.REVIEW_CHECK,
        PrimaryIntent.PLANNING,
        PrimaryIntent.COMPARISON,
        PrimaryIntent.NEARBY,
        PrimaryIntent.REALTIME_CHECK,
        PrimaryIntent.CLARIFICATION,
    }
)

_TASK_TO_INTENT: dict[NonLookupTaskClass, PrimaryIntent] = {
    "advisory": PrimaryIntent.ADVISORY,
    "review_check": PrimaryIntent.REVIEW_CHECK,
    "planning": PrimaryIntent.PLANNING,
    "comparison": PrimaryIntent.COMPARISON,
    "nearby": PrimaryIntent.NEARBY,
    "realtime_check": PrimaryIntent.REALTIME_CHECK,
    "clarification": PrimaryIntent.CLARIFICATION,
}

_INTENT_TO_TASK: dict[PrimaryIntent, NonLookupTaskClass] = {
    intent: task for task, intent in _TASK_TO_INTENT.items()
}

_TASK_CLAIMS: dict[NonLookupTaskClass, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "advisory": (
        ("review_summary", "seasonality", "route_plan"),
        ("opening_hours", "weather", "crowd_risk", "accessibility"),
    ),
    "review_check": (
        ("review_summary", "value_for_money", "crowd_risk"),
        ("commercialization_risk", "queue_risk", "family_friendly"),
    ),
    "planning": (
        ("route_plan", "duration", "distance", "opening_hours"),
        ("traffic_status", "weather", "crowd_risk", "review_summary"),
    ),
    "comparison": (
        ("review_summary", "route_plan", "duration", "crowd_risk"),
        ("ticket_price", "seasonality", "family_friendly", "value_for_money"),
    ),
    "nearby": (
        ("nearby_poi", "nearby_food"),
        ("distance", "rating_candidate", "review_summary"),
    ),
    "realtime_check": (
        ("current_weather", "traffic_status", "current_crowd", "temporary_closure"),
        ("forecast", "congestion_risk", "queue_time"),
    ),
    "clarification": (
        ("entity_resolution", "disambiguation"),
        ("place_lookup",),
    ),
}

_TASK_STATE_CHAINS: dict[NonLookupTaskClass, tuple[str, ...]] = {
    "advisory": (
        "S1 Context",
        "S2 Understanding / IntentProfile",
        "S3 AdvisoryResponseContract",
        "S4 RegionGate",
        "S5 AdvisoryEvidencePlanning",
        "S6 EvidenceAccumulation",
        "S7 AdvisoryEvidenceJudge",
        "S8 AdvisoryComposer",
    ),
    "review_check": (
        "S1 Context",
        "S2 Understanding",
        "S3 ReviewCheckContract",
        "S5 ReviewSignalRetrieval",
        "S6 EvidenceAccumulation",
        "S7 ReviewSignalAggregation",
        "S8 ReviewInsightComposer",
    ),
    "planning": (
        "S1 Context",
        "S2 Understanding",
        "S3 PlanningContract",
        "S4 RegionGate",
        "S5 PlanningEvidenceRetrieval",
        "S6 EvidenceAccumulation",
        "S7 RouteFeasibilityJudge",
        "Optional GapFill",
        "S8 ItineraryComposer",
    ),
    "comparison": (
        "S1 Context",
        "S2 MultiPlaceUnderstanding",
        "S3 ComparisonContract",
        "S5 MultiPlaceEvidenceRetrieval",
        "S6 EvidenceAccumulation",
        "S7 AlignedComparisonJudge",
        "S8 ComparisonComposer",
    ),
    "nearby": (
        "S1 Context",
        "S2 NearbyUnderstanding",
        "S3 NearbyContract",
        "S5 NearbyPOIRetrieval",
        "S6 EvidenceAccumulation",
        "S7 NearbyCandidateJudge",
        "S8 NearbyRecommendationComposer",
    ),
    "realtime_check": (
        "S1 Context",
        "S2 RealtimeUnderstanding",
        "S3 RealtimeContract",
        "S5 RealtimeEvidenceRetrieval",
        "S6 EvidenceAccumulation",
        "S7 FreshnessJudge",
        "S8 RealtimeComposer",
    ),
    "clarification": (
        "S1 Context",
        "S2 Understanding",
        "S3 ClarificationPolicy",
        "Optional MinimalProbe",
        "S8 ClarificationComposer",
        "END",
    ),
}

_TASK_SOURCE_FAMILIES: dict[NonLookupTaskClass, tuple[str, ...]] = {
    "advisory": (
        "review_platform_provider",
        "weather_provider",
        "route_provider",
        "official_web_provider",
        "model_prior_provider",
    ),
    "review_check": (
        "review_platform_provider",
        "search_provider",
        "crawler_provider",
        "baidu_lbs_provider",
    ),
    "planning": (
        "baidu_lbs_provider",
        "route_provider",
        "official_web_provider",
        "weather_provider",
        "review_platform_provider",
    ),
    "comparison": (
        "baidu_lbs_provider",
        "review_platform_provider",
        "route_provider",
        "official_web_provider",
        "weather_provider",
    ),
    "nearby": (
        "baidu_lbs_provider",
        "review_platform_provider",
        "route_provider",
        "crawler_provider",
    ),
    "realtime_check": (
        "weather_provider",
        "baidu_lbs_provider",
        "official_web_provider",
        "crawler_provider",
        "review_platform_provider",
    ),
    "clarification": (
        "baidu_lbs_provider",
        "search_provider",
    ),
}

_REVIEW_CLAIMS = {
    "review_summary",
    "review_aspect",
    "value_for_money",
    "crowd_risk",
    "queue_risk",
    "commercialization_risk",
    "family_friendly",
    "elderly_suitability",
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

_HARD_FACT_CLAIMS = {
    "ticket_price",
    "opening_hours",
    "temporary_closure",
    "reservation_policy",
    "seasonal_operation_status",
}

_ROUTE_CLAIMS = {"route_plan", "duration", "distance", "route_steps", "traffic_status"}
_NEARBY_CLAIMS = {"nearby_poi", "nearby_food", "nearby_hotel", "nearby_parking", "nearby_toilet"}


class TaskChainProfile(BaseModel):
    task_class: NonLookupTaskClass
    primary_intent: PrimaryIntent
    retrieval_mode: str
    s7_policy: str
    compose_mode: str
    task_chain: list[str] = Field(default_factory=list)
    information_domains: list[str] = Field(default_factory=list)
    source_family_plan: list[str] = Field(default_factory=list)
    primary_claims: list[str] = Field(default_factory=list)
    secondary_claims: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    preferred_subagents: list[str] = Field(default_factory=list)


class TaskDebugTrace(BaseModel):
    task_class: NonLookupTaskClass
    task_chain: list[str] = Field(default_factory=list)
    selected_state_path: list[str] = Field(default_factory=list)
    primary_claims: list[str] = Field(default_factory=list)
    secondary_claims: list[str] = Field(default_factory=list)
    source_family_plan: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[str] = Field(default_factory=list)
    attempted_source_families: list[str] = Field(default_factory=list)
    skipped_with_reason: list[dict] = Field(default_factory=list)
    evidence_count_by_family: dict[str, int] = Field(default_factory=dict)
    claim_decisions: list[dict] = Field(default_factory=list)
    adoption_levels: dict[str, str] = Field(default_factory=dict)
    user_visible_limitations: list[str] = Field(default_factory=list)
    internal_debug_limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class NearbyCandidate:
    evidence_id: str
    name: str
    category: str
    distance_m: int | None
    reason: str
    accepted: bool


def non_lookup_task_classes() -> list[NonLookupTaskClass]:
    return list(_TASK_TO_INTENT.keys())


def is_non_lookup_task(state: TravelAgentState) -> bool:
    return resolve_non_lookup_task_class(state) is not None


def resolve_non_lookup_task_class(state: TravelAgentState) -> NonLookupTaskClass | None:
    profile = state.intent_profile
    if profile and profile.primary_intent in _INTENT_TO_TASK:
        return _INTENT_TO_TASK[profile.primary_intent]

    frame = state.semantic_frame
    if not frame:
        return None
    if frame.decision_type == DecisionType.NEARBY_SEARCH:
        return "nearby"
    if frame.decision_type == DecisionType.ROUTE_PLAN or frame.task_family == TaskFamily.PLANNING:
        return "planning"
    if frame.task_family == TaskFamily.COMPARISON:
        return "comparison"
    if frame.requires_live_data or frame.task_family in {TaskFamily.WEATHER, TaskFamily.CROWD}:
        return "realtime_check"
    if frame.needs_clarification:
        return "clarification"
    if _looks_like_review_check(frame):
        return "review_check"
    if frame.task_family in {TaskFamily.SUITABILITY, TaskFamily.ADVISORY}:
        return "advisory"
    return None


def build_non_lookup_task_profile(state: TravelAgentState) -> TaskChainProfile | None:
    task_class = resolve_non_lookup_task_class(state)
    if not task_class:
        return None
    intent = _TASK_TO_INTENT[task_class]
    strategy = _strategy_for(state, intent)
    primary, secondary = _TASK_CLAIMS[task_class]
    domain_plan = S5DomainPlanner().plan(
        state.response_contract,
        state.semantic_frame,
        evidence=state.evidence,
        intent_profile=state.intent_profile or _profile_for_task(task_class),
        intent_strategy=strategy,
    )
    domains = [d.value for d in domain_plan.domains] or [d.value for d in strategy.domain_priority]
    blocked = set(strategy.forbidden_tools)
    blocked.update(domain_plan.effective_forbidden_tool_names())
    return TaskChainProfile(
        task_class=task_class,
        primary_intent=intent,
        retrieval_mode=strategy.retrieval_mode,
        s7_policy=strategy.s7_policy,
        compose_mode=strategy.compose_mode,
        task_chain=list(_TASK_STATE_CHAINS[task_class]),
        information_domains=domains,
        source_family_plan=_source_family_plan(task_class, domain_plan.provider_groups()),
        primary_claims=list(primary),
        secondary_claims=list(secondary),
        allowed_tools=list(dict.fromkeys(strategy.preferred_tools)),
        blocked_tools=sorted(blocked),
        preferred_subagents=list(strategy.preferred_subagents),
    )


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

    requirements = _claim_requirements_for_task(profile, state)
    contract = ResponseContract(
        user_goal_summary=state.raw_user_query,
        claim_requirements=requirements,
    )
    contract.composition_policy.answer_style = _composition_style(profile.task_class)
    if profile.task_class == "clarification":
        contract.clarification_policy.should_ask = True
        contract.clarification_policy.reason = "missing or ambiguous target"
        contract.clarification_policy.question = build_minimal_clarification_question(state)
    state.response_contract = contract
    return contract


def evaluate_non_lookup_task_evidence(state: TravelAgentState) -> EvidenceDecisionReport:
    """Run S7 for the active non-lookup task and apply task-specific adoption rules."""
    profile = build_non_lookup_task_profile(state)
    if not profile:
        report = evaluate_evidence(state, target_label=_target_label(state))
        state.evidence_decision_report = report
        return report

    ensure_non_lookup_task_contract(state)
    if profile.task_class == "clarification":
        report = _clarification_report(state)
    else:
        report = evaluate_evidence(state, target_label=_target_label(state))
        _apply_task_s7_policy(state, profile, report)
    state.evidence_decision_report = report
    _attach_task_trace(state, build_non_lookup_task_debug_trace(state, report))
    return report


def prepare_non_lookup_task_compose_context(state: TravelAgentState, compose_kwargs: dict) -> dict:
    profile = build_non_lookup_task_profile(state)
    if not profile:
        return compose_kwargs
    report = state.evidence_decision_report or evaluate_non_lookup_task_evidence(state)
    trace = build_non_lookup_task_debug_trace(state, report)
    draft = build_non_lookup_task_draft(state, report)
    return {
        **compose_kwargs,
        "compose_mode": profile.compose_mode,
        "target_label": compose_kwargs.get("target_label") or _target_label(state),
        "non_lookup_task_profile": profile.model_dump(mode="json"),
        "non_lookup_task_trace": trace.model_dump(mode="json"),
        "task_adoption_summary": trace.adoption_levels,
        "task_composer_draft": draft.model_dump(mode="json"),
    }


def should_use_non_lookup_task_context(state: TravelAgentState) -> bool:
    task = resolve_non_lookup_task_class(state)
    return bool(task and task != "nearby")


def build_non_lookup_task_debug_trace(
    state: TravelAgentState,
    report: EvidenceDecisionReport | None = None,
) -> TaskDebugTrace:
    profile = build_non_lookup_task_profile(state)
    if not profile:
        profile = _empty_profile("advisory")
    report = report or state.evidence_decision_report
    claim_rows = []
    adoption_levels: dict[str, str] = {}
    if report:
        for decision in report.claim_decisions:
            row = decision.model_dump(mode="json")
            claim_rows.append(row)
            adoption_levels[decision.claim_type] = (
                decision.adoption_level or _adoption_level_from_decision(decision)
            )

    skipped = _skipped_tools(state, profile)
    return TaskDebugTrace(
        task_class=profile.task_class,
        task_chain=profile.task_chain,
        selected_state_path=_selected_state_path(state, profile),
        primary_claims=profile.primary_claims,
        secondary_claims=profile.secondary_claims,
        source_family_plan=profile.source_family_plan,
        allowed_tools=profile.allowed_tools,
        blocked_tools=profile.blocked_tools,
        attempted_source_families=_attempted_source_families(state.tool_traces),
        skipped_with_reason=skipped,
        evidence_count_by_family=_evidence_count_by_family(state.evidence),
        claim_decisions=claim_rows,
        adoption_levels=adoption_levels,
        user_visible_limitations=list(dict.fromkeys(state.user_visible_limitations + state.limitations)),
        internal_debug_limitations=list(dict.fromkeys(state.internal_debug_limitations)),
    )


def build_non_lookup_task_draft(
    state: TravelAgentState,
    report: EvidenceDecisionReport | None = None,
) -> FinalAnswerDraft:
    profile = build_non_lookup_task_profile(state) or _empty_profile("advisory")
    report = report or state.evidence_decision_report
    target = _target_label(state)
    cited = _adopted_evidence_ids(report)
    values = _adopted_values_by_claim(state.evidence, cited)
    limitations = list(dict.fromkeys(state.user_visible_limitations + _decision_limitations(report)))

    if profile.task_class == "review_check":
        bullets = _claim_bullets(values, _REVIEW_CLAIMS) or ["No adoptable review signal was found."]
        return FinalAnswerDraft(
            headline=f"{target} review tendency",
            conclusion=_conclusion_from_report(report, fallback="Review signal is limited."),
            sections=[FinalAnswerSection(title="Review tendency", bullets=bullets)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=profile.compose_mode,
        )
    if profile.task_class == "planning":
        blocks = _time_block_bullets(values)
        return FinalAnswerDraft(
            headline=f"{target} itinerary feasibility",
            conclusion=_conclusion_from_report(report, fallback="Feasibility depends on missing route evidence."),
            sections=[FinalAnswerSection(title="Time blocks", bullets=blocks)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=profile.compose_mode,
        )
    if profile.task_class == "comparison":
        sections = [
            FinalAnswerSection(title="Aligned dimensions", bullets=_aligned_dimension_bullets(report)),
            FinalAnswerSection(title="Evidence asymmetry", bullets=_asymmetry_bullets(report)),
        ]
        return FinalAnswerDraft(
            headline=f"{target} comparison",
            conclusion=_conclusion_from_report(report, fallback="Only aligned evidence should drive the comparison."),
            sections=sections,
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=profile.compose_mode,
        )
    if profile.task_class == "nearby":
        candidates = collect_nearby_candidates(state.evidence)
        bullets = [
            f"{c.name}: {c.distance_m or 'unknown'}m; {c.reason}"
            for c in candidates
            if c.accepted
        ] or ["No nearby candidate passed category and distance filters."]
        return FinalAnswerDraft(
            headline=f"{target} nearby recommendations",
            conclusion="Nearby candidates are listed only when map/category evidence supports them.",
            sections=[FinalAnswerSection(title="Distance and reason", bullets=bullets)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=profile.compose_mode,
        )
    if profile.task_class == "realtime_check":
        bullets = _claim_bullets(values, _LIVE_CLAIMS) or ["No fresh live evidence was adopted."]
        return FinalAnswerDraft(
            headline=f"{target} realtime check",
            conclusion=_conclusion_from_report(report, fallback="Realtime status cannot be confirmed without fresh evidence."),
            sections=[FinalAnswerSection(title="Freshness note", bullets=bullets)],
            limitations=limitations,
            cited_evidence_ids=cited,
            compose_mode=profile.compose_mode,
        )
    if profile.task_class == "clarification":
        question = build_minimal_clarification_question(state)
        return FinalAnswerDraft(
            headline="Need one clarification",
            conclusion=question,
            sections=[FinalAnswerSection(title="Question", bullets=[question])],
            limitations=[],
            cited_evidence_ids=[],
            compose_mode=profile.compose_mode,
        )

    suitable = _claim_bullets(values, {"review_summary", "seasonality", "route_plan", "weather"})
    hard = _claim_bullets(values, _HARD_FACT_CLAIMS | _LIVE_CLAIMS)
    sections = [
        FinalAnswerSection(title="Suitable for", bullets=suitable or ["Evidence is not strong enough for a firm fit statement."]),
        FinalAnswerSection(title="Not suitable for", bullets=hard or ["No hard/live blocker was adopted from evidence."]),
    ]
    return FinalAnswerDraft(
        headline=f"{target} advisory",
        conclusion=_conclusion_from_report(report, fallback="Recommendation must stay bounded by available evidence."),
        sections=sections,
        limitations=limitations,
        cited_evidence_ids=cited,
        compose_mode=profile.compose_mode,
    )


def collect_nearby_candidates(evidence: Iterable) -> list[NearbyCandidate]:
    candidates: list[NearbyCandidate] = []
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            ct = _claim_type_value(claim.claim_type)
            if ct not in {
                ClaimType.FOOD.value,
                ClaimType.LODGING.value,
                ClaimType.PLACE_CANDIDATES.value,
                "nearby_poi",
                "nearby_food",
                "nearby_hotel",
                "nearby_parking",
                "nearby_toilet",
            }:
                continue
            nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
            name = str(nv.get("name") or claim.value or "").strip()
            category = str(nv.get("category") or nv.get("nearby_category") or ct).lower()
            distance = _as_int(nv.get("distance_m") or nv.get("distance"))
            wrong_category = bool(nv.get("category_match") is False or nv.get("wrong_category"))
            too_far = distance is not None and distance > 3000
            accepted = bool(name) and not wrong_category and not too_far
            if not accepted:
                reason = "filtered: wrong category" if wrong_category else "filtered: too far"
            else:
                reason = str(nv.get("reason") or "category and distance evidence present")
            candidates.append(
                NearbyCandidate(
                    evidence_id=ev.evidence_id,
                    name=name,
                    category=category,
                    distance_m=distance,
                    reason=reason,
                    accepted=accepted,
                )
            )
    return candidates


def build_minimal_clarification_question(state: TravelAgentState) -> str:
    related = related_poi_not_disambiguation_same_scenic_area(state)
    if related:
        return "Do you want recommendations ranked within the same scenic area, or a specific entrance/service point?"
    frame = state.semantic_frame
    if frame and frame.place_ambiguity and frame.place_ambiguity.is_ambiguous:
        labels = [
            " ".join(part for part in (c.region, c.city, c.name) if part).strip()
            for c in frame.place_ambiguity.candidates[:3]
        ]
        labels = [x for x in labels if x]
        if labels:
            return "Which place do you mean: " + " / ".join(labels) + "?"
    if frame and frame.missing_slots:
        slot = frame.missing_slots[0]
        return f"Please clarify {slot}."
    return "Which exact place or city do you mean?"


def related_poi_not_disambiguation_same_scenic_area(state: TravelAgentState) -> bool:
    candidates = _candidate_dicts(state)
    if len(candidates) < 2:
        return False
    parents = {
        str(c.get("parent_place") or c.get("scenic_area") or c.get("parent") or "").strip()
        for c in candidates
    }
    parents.discard("")
    if len(parents) == 1:
        return True
    cities = {str(c.get("city") or "").strip() for c in candidates}
    cities.discard("")
    names = [str(c.get("name") or "").strip() for c in candidates]
    return len(cities) <= 1 and any("gate" in n.lower() or "entrance" in n.lower() for n in names)


def build_sample_trace_summaries() -> dict[str, dict]:
    return {
        task: build_non_lookup_task_debug_trace(_sample_state(task)).model_dump(mode="json")
        for task in non_lookup_task_classes()
    }


def _apply_task_s7_policy(
    state: TravelAgentState,
    profile: TaskChainProfile,
    report: EvidenceDecisionReport,
) -> None:
    for decision in report.claim_decisions:
        if profile.task_class == "review_check" and _is_review_claim(decision.claim_type):
            _apply_review_signal_level(state, decision)
        elif profile.task_class == "realtime_check" and _is_live_claim(decision.claim_type):
            _apply_realtime_level(state, decision)
        elif profile.task_class == "comparison":
            _apply_comparison_level(state, decision)
        elif profile.task_class == "planning" and decision.claim_type in _ROUTE_CLAIMS:
            _apply_planning_level(state, decision)
        elif profile.task_class == "nearby" and (
            decision.claim_type in _NEARBY_CLAIMS or decision.claim_family == "nearby_recommendation"
        ):
            _apply_nearby_level(state, decision)
        elif profile.task_class == "advisory":
            _apply_advisory_level(state, decision)
        decision.adoption_level = _adoption_level_from_decision(decision)


def _apply_review_signal_level(state: TravelAgentState, decision: ClaimDecision) -> None:
    review_sources = _sources_for_claim(state.evidence, _REVIEW_CLAIMS)
    anecdotal = _only_anecdotal_review(state.evidence)
    if len(review_sources) >= 2:
        decision.coverage_quality = "strong"
        decision.adoption = "adopt"
        decision.reason = f"{decision.reason}; multi_source_consistent"
        decision.adoption_level = "strong"
    elif len(review_sources) == 1 and anecdotal:
        decision.coverage_quality = "weak"
        decision.adoption = "adopt_with_limitation"
        decision.reason = f"{decision.reason}; anecdotal_only"
        decision.must_show_limitation = True
        decision.user_visible_limitations.append("Only a single extreme/anecdotal review signal was found.")
    elif len(review_sources) == 1:
        decision.coverage_quality = "partial"
        decision.adoption = "adopt_with_limitation"
        decision.reason = f"{decision.reason}; single_source_partial"
        decision.must_show_limitation = True
        decision.user_visible_limitations.append("Review tendency is based on one source family only.")
    else:
        decision.coverage_quality = "none"
        decision.adoption = "refuse_to_guess"
        decision.reason = f"{decision.reason}; no_review_evidence"


def _apply_realtime_level(state: TravelAgentState, decision: ClaimDecision) -> None:
    fresh_ids = set()
    stale_or_prior = False
    for ev in state.evidence:
        if not isinstance(ev, Evidence) or not _evidence_has_claim(ev, _LIVE_CLAIMS):
            continue
        if ev.source_type == SourceType.MODEL_PRIOR:
            stale_or_prior = True
            continue
        if ev.data_freshness in {DataFreshness.LIVE, DataFreshness.RECENT}:
            fresh_ids.add(ev.evidence_id)
        else:
            stale_or_prior = True
    if fresh_ids:
        decision.adopted_evidence_ids = list(dict.fromkeys(decision.adopted_evidence_ids + list(fresh_ids)))
        decision.coverage_quality = "strong" if any(_freshness_by_id(state.evidence, eid) == DataFreshness.LIVE for eid in fresh_ids) else "partial"
        decision.adoption = "adopt" if decision.coverage_quality == "strong" else "adopt_with_limitation"
        decision.reason = f"{decision.reason}; freshness_checked"
    else:
        decision.coverage_quality = "none" if stale_or_prior else decision.coverage_quality
        decision.adoption = "refuse_to_guess"
        decision.adopted_evidence_ids = []
        decision.reason = f"{decision.reason}; no_fresh_live_evidence"
        decision.user_visible_limitations.append("Realtime status could not be confirmed from fresh tool evidence.")


def _apply_comparison_level(state: TravelAgentState, decision: ClaimDecision) -> None:
    places = _places_with_claim(state.evidence, decision.claim_type)
    required_places = _comparison_places(state)
    if len(required_places) >= 2 and len(places.intersection(required_places)) < 2:
        decision.adoption = "refuse_to_guess"
        decision.coverage_quality = "none" if not places else "weak"
        decision.adopted_evidence_ids = []
        decision.reason = f"{decision.reason}; evidence_asymmetry"
        decision.user_visible_limitations.append(
            f"Comparison dimension '{decision.claim_type}' lacks aligned evidence for all places."
        )
    elif len(required_places) >= 2:
        decision.reason = f"{decision.reason}; aligned_dimension"


def _apply_planning_level(state: TravelAgentState, decision: ClaimDecision) -> None:
    if _planning_origin_missing(state):
        decision.adoption = "ask_clarification"
        decision.coverage_quality = "none"
        decision.adopted_evidence_ids = []
        decision.reason = f"{decision.reason}; missing_origin"
        decision.user_visible_limitations.append("A route plan needs a start point or enough ordered places.")
    elif decision.coverage_quality == "none":
        decision.adoption = "adopt_with_limitation"
        decision.reason = f"{decision.reason}; route_gap"


def _apply_nearby_level(state: TravelAgentState, decision: ClaimDecision) -> None:
    candidates = collect_nearby_candidates(state.evidence)
    accepted = [c for c in candidates if c.accepted]
    if not accepted:
        decision.adoption = "refuse_to_guess"
        decision.coverage_quality = "none"
        decision.adopted_evidence_ids = []
        decision.reason = f"{decision.reason}; no_nearby_candidate_after_filter"
    else:
        decision.adopted_evidence_ids = list(dict.fromkeys(decision.adopted_evidence_ids + [c.evidence_id for c in accepted]))
        decision.coverage_quality = "strong" if len(accepted) >= 3 else "partial"
        decision.adoption = "adopt" if decision.coverage_quality == "strong" else "adopt_with_limitation"
        if len(accepted) < len(candidates):
            decision.user_visible_limitations.append("Some nearby candidates were filtered for distance or category mismatch.")


def _apply_advisory_level(state: TravelAgentState, decision: ClaimDecision) -> None:
    if decision.claim_type in _HARD_FACT_CLAIMS | _LIVE_CLAIMS:
        adopted = [_evidence_by_id(state.evidence, eid) for eid in decision.adopted_evidence_ids]
        if any(ev and ev.source_type == SourceType.MODEL_PRIOR for ev in adopted):
            decision.adoption = "refuse_to_guess"
            decision.coverage_quality = "none"
            decision.adopted_evidence_ids = []
            decision.reason = f"{decision.reason}; hard_fact_subclaim_requires_tool_evidence"
            decision.user_visible_limitations.append("Hard/live subclaims were not adopted from model prior.")
    elif decision.coverage_quality == "none":
        decision.adoption = "adopt_with_limitation"
        decision.reason = f"{decision.reason}; advisory_open_claim_limit"


def _clarification_report(state: TravelAgentState) -> EvidenceDecisionReport:
    question = build_minimal_clarification_question(state)
    if related_poi_not_disambiguation_same_scenic_area(state):
        decision = ClaimDecision(
            claim_type="related_poi_ranking",
            claim_family="clarification",
            required=True,
            coverage_quality="partial",
            adoption="adopt_with_limitation",
            reason="same_scenic_area_related_poi_not_disambiguation",
            user_visible_limitations=[question],
        )
    else:
        decision = ClaimDecision(
            claim_type="disambiguation",
            claim_family="clarification",
            required=True,
            coverage_quality="weak",
            adoption="ask_clarification",
            reason="missing_or_ambiguous_place",
            user_visible_limitations=[question],
        )
    decision.adoption_level = _adoption_level_from_decision(decision)
    return EvidenceDecisionReport(
        claim_decisions=[decision],
        overall_confidence=0.4,
        summary="clarification decision",
    )


def _claim_requirements_for_task(profile: TaskChainProfile, state: TravelAgentState) -> list[ClaimRequirement]:
    claims = list(profile.primary_claims)
    claims.extend(_query_triggered_claims(state, profile.task_class))
    claims = list(dict.fromkeys(claims))
    requirements: list[ClaimRequirement] = []
    for claim in claims:
        hard = claim in _HARD_FACT_CLAIMS
        live = claim in _LIVE_CLAIMS or profile.task_class == "realtime_check"
        family = _claim_family_for_task(profile.task_class, claim)
        requirements.append(
            ClaimRequirement(
                claim_type=claim,
                claim_family=family,
                priority="required" if profile.task_class in {"planning", "comparison", "realtime_check", "clarification"} else "important",
                requires_exact_fact=hard,
                requires_live_data=live,
                model_prior_allowed=profile.task_class == "advisory" and not hard and not live,
                missing_behavior="ask_clarification" if profile.task_class == "clarification" else "refuse_to_guess" if hard or live else "answer_with_limitation",
            )
        )
    return requirements


def _merge_contract_claims(contract: ResponseContract, state: TravelAgentState) -> ResponseContract:
    profile = build_non_lookup_task_profile(state)
    if not profile:
        return contract
    seen = {c.claim_type for c in contract.claim_requirements}
    additions = [c for c in _claim_requirements_for_task(profile, state) if c.claim_type not in seen]
    if additions:
        data = contract.model_dump()
        data["claim_requirements"] = [c.model_dump() for c in contract.claim_requirements + additions]
        return ResponseContract.model_validate(data)
    return contract


def _query_triggered_claims(state: TravelAgentState, task_class: NonLookupTaskClass) -> list[str]:
    text = (state.raw_user_query or "").lower()
    frame_needs = list(state.semantic_frame.information_needs or []) if state.semantic_frame else []
    claims = list(frame_needs)
    if any(token in text for token in ("ticket", "price", "fare", "门票", "票价")):
        claims.append("ticket_price")
    if any(token in text for token in ("open", "closed", "opening", "开放", "关门", "闭园")):
        claims.append("opening_hours")
    if task_class in {"advisory", "realtime_check"} and any(
        token in text for token in ("weather", "rain", "snow", "today", "tomorrow", "天气", "下雨", "今天", "明天")
    ):
        claims.append("current_weather" if task_class == "realtime_check" else "weather")
    if task_class == "planning":
        claims.extend(["route_plan", "duration", "distance"])
    if task_class == "nearby" and not any(c.startswith("nearby_") for c in claims):
        claims.append("nearby_poi")
    return claims


def _strategy_for(state: TravelAgentState, intent: PrimaryIntent) -> IntentStrategy:
    if state.intent_strategy and state.intent_strategy.primary_intent == intent:
        return state.intent_strategy
    profile = state.intent_profile if state.intent_profile and state.intent_profile.primary_intent == intent else None
    return resolve_intent_strategy(profile or _profile_for_intent(intent))  # type: ignore[return-value]


def _profile_for_task(task_class: NonLookupTaskClass) -> IntentProfile:
    return _profile_for_intent(_TASK_TO_INTENT[task_class])


def _profile_for_intent(intent: PrimaryIntent) -> IntentProfile:
    sensitivity = {
        PrimaryIntent.REVIEW_CHECK: EvidenceSensitivity.EXPERIENCE_BASED,
        PrimaryIntent.REALTIME_CHECK: EvidenceSensitivity.LIVE_REQUIRED,
        PrimaryIntent.CLARIFICATION: EvidenceSensitivity.EVIDENCE_PREFERRED,
        PrimaryIntent.ADVISORY: EvidenceSensitivity.MODEL_PRIOR_ALLOWED,
    }.get(intent, EvidenceSensitivity.EVIDENCE_PREFERRED)
    style = {
        PrimaryIntent.PLANNING: AnswerStyle.ITINERARY,
        PrimaryIntent.COMPARISON: AnswerStyle.COMPARISON,
        PrimaryIntent.NEARBY: AnswerStyle.RECOMMENDATION_LIST,
        PrimaryIntent.CLARIFICATION: AnswerStyle.CLARIFICATION,
        PrimaryIntent.REALTIME_CHECK: AnswerStyle.DIRECT_FACT,
    }.get(intent, AnswerStyle.ADVISORY)
    return IntentProfile(
        primary_intent=intent,
        evidence_sensitivity=sensitivity,
        answer_style=style,
        requires_live_data=intent == PrimaryIntent.REALTIME_CHECK,
        requires_review_signal=intent in {PrimaryIntent.REVIEW_CHECK, PrimaryIntent.ADVISORY},
        requires_route_planning=intent == PrimaryIntent.PLANNING,
    )


def _empty_profile(task_class: NonLookupTaskClass) -> TaskChainProfile:
    intent = _TASK_TO_INTENT[task_class]
    strategy = resolve_intent_strategy(_profile_for_task(task_class))
    assert strategy is not None
    primary, secondary = _TASK_CLAIMS[task_class]
    return TaskChainProfile(
        task_class=task_class,
        primary_intent=intent,
        retrieval_mode=strategy.retrieval_mode,
        s7_policy=strategy.s7_policy,
        compose_mode=strategy.compose_mode,
        task_chain=list(_TASK_STATE_CHAINS[task_class]),
        source_family_plan=list(_TASK_SOURCE_FAMILIES[task_class]),
        primary_claims=list(primary),
        secondary_claims=list(secondary),
        allowed_tools=list(strategy.preferred_tools),
        blocked_tools=list(strategy.forbidden_tools),
        preferred_subagents=list(strategy.preferred_subagents),
    )


def _source_family_plan(task_class: NonLookupTaskClass, provider_groups: list[ProviderGroup]) -> list[str]:
    values = [p.value for p in provider_groups]
    if values:
        return list(dict.fromkeys(values))
    return list(_TASK_SOURCE_FAMILIES[task_class])


def _composition_style(task_class: NonLookupTaskClass) -> str:
    return {
        "comparison": "comparison",
        "planning": "itinerary",
        "clarification": "clarification",
    }.get(task_class, "advisory")


def _claim_family_for_task(task_class: NonLookupTaskClass, claim: str) -> str:
    if claim in _REVIEW_CLAIMS:
        return "review_experience"
    if claim in _LIVE_CLAIMS:
        return "live_fact"
    if claim in _ROUTE_CLAIMS:
        return "route_planning"
    if claim in _NEARBY_CLAIMS:
        return "nearby_recommendation"
    if claim in _HARD_FACT_CLAIMS:
        return "hard_fact"
    if task_class == "comparison":
        return "comparison"
    if task_class == "clarification":
        return "geo_fact"
    return "open_advice"


def _looks_like_review_check(frame: SemanticFrame) -> bool:
    text = f"{frame.raw_query} {frame.normalized_request}".lower()
    return any(
        token in text
        for token in (
            "review",
            "overrated",
            "commercial",
            "crowd",
            "评价",
            "坑",
            "商业化",
            "高估",
            "人多",
        )
    )


def _selected_state_path(state: TravelAgentState, profile: TaskChainProfile) -> list[str]:
    if profile.task_class == "clarification" and profile.primary_intent == PrimaryIntent.CLARIFICATION:
        return [s for s in profile.task_chain if s != "S4 RegionGate"]
    if state.evidence_decision_report and state.evidence_decision_report.evidence_gap_requests:
        return profile.task_chain
    return [s for s in profile.task_chain if s != "Optional GapFill"]


def _skipped_tools(state: TravelAgentState, profile: TaskChainProfile) -> list[dict]:
    rows: list[dict] = []
    for tool in profile.blocked_tools:
        rows.append({"tool": tool, "reason": "blocked_by_task_policy"})
    for trace in state.tool_traces or []:
        if trace.status != "ok":
            rows.append({"tool": trace.tool_name, "reason": trace.error or trace.status})
    return rows


def _attempted_source_families(traces: list[ToolTrace]) -> list[str]:
    families = []
    for trace in traces or []:
        provider = trace.provider or _provider_family_from_tool(trace.tool_name)
        if provider:
            families.append(provider)
    return list(dict.fromkeys(families))


def _evidence_count_by_family(evidence: list) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for ev in evidence or []:
        if isinstance(ev, Evidence):
            counts[_source_family_from_evidence(ev)] += 1
    return dict(counts)


def _source_family_from_evidence(ev: Evidence) -> str:
    if ev.source_type == SourceType.WEATHER_API:
        return "weather_provider"
    if ev.source_type in {SourceType.MAP, SourceType.TRANSIT_API}:
        return "baidu_lbs_provider"
    if ev.source_type == SourceType.REVIEW_PLATFORM:
        return "review_platform_provider"
    if ev.source_type == SourceType.OFFICIAL:
        return "official_web_provider"
    if ev.source_type in {SourceType.WEB, SourceType.BLOG, SourceType.SOCIAL}:
        return "search_provider"
    if ev.source_type == SourceType.MODEL_PRIOR:
        return "model_prior_provider"
    return ev.source_type.value


def _provider_family_from_tool(tool_name: str) -> str:
    if "weather" in tool_name or "openmeteo" in tool_name:
        return "weather_provider"
    if "baidu" in tool_name or "route" in tool_name or "osm" in tool_name:
        return "baidu_lbs_provider"
    if "review" in tool_name or "dianping" in tool_name or "ctrip" in tool_name:
        return "review_platform_provider"
    if "official" in tool_name or "browser" in tool_name:
        return "official_web_provider"
    if "search" in tool_name or "wiki" in tool_name:
        return "search_provider"
    if "knowledge_prior" in tool_name:
        return "model_prior_provider"
    return "unknown_provider"


def _sources_for_claim(evidence: list, claim_types: set[str]) -> set[str]:
    out = set()
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if _evidence_has_claim(ev, claim_types):
            out.add(f"{_source_family_from_evidence(ev)}:{ev.source_name}")
    return out


def _only_anecdotal_review(evidence: list) -> bool:
    texts = []
    for ev in evidence or []:
        if not isinstance(ev, Evidence) or not _evidence_has_claim(ev, _REVIEW_CLAIMS):
            continue
        texts.extend(str(c.value).lower() for c in ev.claims)
    if not texts:
        return False
    joined = " ".join(texts)
    markers = ("worst", "never again", "avoid", "terrible", "垃圾", "千万别", "最差", "踩雷")
    return any(m in joined for m in markers)


def _evidence_has_claim(ev: Evidence, claim_types: set[str]) -> bool:
    return any(_claim_type_value(c.claim_type) in claim_types for c in ev.claims)


def _claim_type_value(claim_type) -> str:
    return claim_type.value if hasattr(claim_type, "value") else str(claim_type)


def _is_review_claim(claim: str) -> bool:
    return claim in _REVIEW_CLAIMS or "review" in claim


def _is_live_claim(claim: str) -> bool:
    return claim in _LIVE_CLAIMS or "current" in claim or "traffic" in claim


def _freshness_by_id(evidence: list, evidence_id: str) -> DataFreshness | None:
    ev = _evidence_by_id(evidence, evidence_id)
    return ev.data_freshness if ev else None


def _evidence_by_id(evidence: list, evidence_id: str) -> Evidence | None:
    for ev in evidence or []:
        if isinstance(ev, Evidence) and ev.evidence_id == evidence_id:
            return ev
    return None


def _places_with_claim(evidence: list, claim_type: str) -> set[str]:
    aliases = {claim_type}
    if claim_type == "route_plan":
        aliases.update(_ROUTE_CLAIMS)
    if claim_type == "review_summary":
        aliases.update(_REVIEW_CLAIMS)
    places = set()
    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        if _evidence_has_claim(ev, aliases) and ev.place_name:
            places.add(ev.place_name)
    return places


def _comparison_places(state: TravelAgentState) -> set[str]:
    if state.semantic_frame and state.semantic_frame.entities.places:
        return set(state.semantic_frame.entities.places)
    if state.comparison_peer_places:
        return {p for p in [state.comparison_active_place, *state.comparison_peer_places] if p}
    return set()


def _planning_origin_missing(state: TravelAgentState) -> bool:
    frame = state.semantic_frame
    places = frame.entities.places if frame and frame.entities else []
    context_start = getattr(state.conversation_context, "start_location", None)
    has_start = bool(context_start or (state.user_goal and state.user_goal.start_location))
    if len(places) >= 2:
        return False
    return not has_start


def _candidate_dicts(state: TravelAgentState) -> list[dict]:
    out: list[dict] = []
    if state.semantic_frame and state.semantic_frame.place_ambiguity:
        for c in state.semantic_frame.place_ambiguity.candidates:
            out.append(c.model_dump())
    structured = state.structured_result or {}
    for c in structured.get("place_disambiguation_candidates") or []:
        if isinstance(c, dict):
            out.append(c)
    for ev in state.evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            if claim.claim_type != ClaimType.PLACE_CANDIDATES:
                continue
            nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
            bucket = nv.get("candidates") or claim.value
            if isinstance(bucket, list):
                out.extend(c for c in bucket if isinstance(c, dict))
    return out


def _target_label(state: TravelAgentState) -> str:
    frame = state.semantic_frame
    if frame and frame.entities.places:
        return " vs ".join(frame.entities.places[:3]) if len(frame.entities.places) > 1 else frame.entities.places[0]
    if frame and frame.entities.city:
        return frame.entities.city
    return state.raw_user_query[:30] or "destination"


def _adoption_level_from_decision(decision: ClaimDecision) -> str:
    if decision.adoption == "adopt" and decision.coverage_quality == "strong":
        return "strong"
    if decision.adoption in {"adopt", "adopt_with_limitation"} and decision.coverage_quality in {"partial", "strong"}:
        return "partial"
    if decision.adoption == "candidate_only":
        return "candidate_only"
    if decision.adoption in {"refuse_to_guess", "ask_clarification", "omit"}:
        return "rejected" if decision.coverage_quality != "none" else "no_evidence"
    return "weak"


def _attach_task_trace(state: TravelAgentState, trace: TaskDebugTrace) -> None:
    structured = dict(state.structured_result or {})
    structured["non_lookup_task_trace"] = trace.model_dump(mode="json")
    structured["non_lookup_task_class"] = trace.task_class
    state.structured_result = structured


def _adopted_evidence_ids(report: EvidenceDecisionReport | None) -> list[str]:
    if not report:
        return []
    out: list[str] = []
    for decision in report.claim_decisions:
        if decision.adoption in {"adopt", "adopt_with_limitation", "candidate_only"}:
            out.extend(decision.adopted_evidence_ids)
    return list(dict.fromkeys(out))


def _adopted_values_by_claim(evidence: list, evidence_ids: list[str]) -> dict[str, list[str]]:
    allowed = set(evidence_ids)
    values: dict[str, list[str]] = defaultdict(list)
    for ev in evidence or []:
        if not isinstance(ev, Evidence) or (allowed and ev.evidence_id not in allowed):
            continue
        for claim in ev.claims:
            ct = _claim_type_value(claim.claim_type)
            val = str(claim.value).strip()
            if val:
                values[ct].append(val)
    return dict(values)


def _claim_bullets(values: dict[str, list[str]], claim_types: set[str]) -> list[str]:
    bullets = []
    for claim in claim_types:
        for value in values.get(claim, [])[:2]:
            bullets.append(f"{claim}: {value}")
    return bullets[:6]


def _decision_limitations(report: EvidenceDecisionReport | None) -> list[str]:
    if not report:
        return []
    out: list[str] = []
    for decision in report.claim_decisions:
        out.extend(decision.user_visible_limitations)
        out.extend(decision.limitations)
    return list(dict.fromkeys(out))


def _conclusion_from_report(report: EvidenceDecisionReport | None, *, fallback: str) -> str:
    if not report or not report.claim_decisions:
        return fallback
    adopted = [d.claim_type for d in report.claim_decisions if d.adoption in {"adopt", "adopt_with_limitation", "candidate_only"}]
    refused = [d.claim_type for d in report.claim_decisions if d.adoption in {"refuse_to_guess", "ask_clarification"}]
    if adopted:
        tail = f"; limited on {', '.join(refused[:3])}" if refused else ""
        return f"Adopted evidence for {', '.join(adopted[:4])}{tail}."
    return fallback


def _time_block_bullets(values: dict[str, list[str]]) -> list[str]:
    bullets = _claim_bullets(values, _ROUTE_CLAIMS | {"opening_hours"})
    return bullets or ["Do not build a detailed timetable until route duration and opening-hours evidence exist."]


def _aligned_dimension_bullets(report: EvidenceDecisionReport | None) -> list[str]:
    if not report:
        return ["No comparison dimensions evaluated."]
    out = [
        f"{d.claim_type}: {d.coverage_quality}/{d.adoption}"
        for d in report.claim_decisions
        if "evidence_asymmetry" not in d.reason
    ]
    return out or ["No aligned dimension is strong enough for a direct comparison."]


def _asymmetry_bullets(report: EvidenceDecisionReport | None) -> list[str]:
    if not report:
        return ["Evidence asymmetry was not evaluated."]
    out = [
        f"{d.claim_type}: {', '.join(d.user_visible_limitations) or d.reason}"
        for d in report.claim_decisions
        if "evidence_asymmetry" in d.reason or d.user_visible_limitations
    ]
    return out or ["No evidence asymmetry detected in evaluated dimensions."]


def _as_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace("m", "").strip()))
    except (TypeError, ValueError):
        return None


def _sample_state(task_class: NonLookupTaskClass) -> TravelAgentState:
    frame = SemanticFrame(raw_query=f"sample {task_class}")
    frame.entities.places = ["Sample Place"]
    frame.information_needs = list(_TASK_CLAIMS[task_class][0])
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
    state = TravelAgentState(session_id="sample", query_id=task_class, raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = _profile_for_task(task_class)
    state.intent_strategy = resolve_intent_strategy(state.intent_profile)
    ensure_non_lookup_task_contract(state)
    return state
