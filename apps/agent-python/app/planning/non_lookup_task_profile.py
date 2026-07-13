"""Pure classification and S5 profile planning for non-lookup travel tasks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.planning.intent_strategy_registry import IntentStrategy, resolve_intent_strategy
from app.planning.s5_domain_planner import S5DomainPlanner
from app.planning.s5_information_domain import ProviderGroup
from app.understanding.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.understanding.semantic_frame_model import DecisionType, SemanticFrame, TaskFamily


TravelAgentState = Any

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

def _strategy_for(state: TravelAgentState, intent: PrimaryIntent) -> IntentStrategy:
    if state.intent_strategy and state.intent_strategy.primary_intent == intent:
        return state.intent_strategy
    profile = state.intent_profile if state.intent_profile and state.intent_profile.primary_intent == intent else None
    return resolve_intent_strategy(profile or _profile_for_intent(intent))

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

def composition_style(task_class: NonLookupTaskClass) -> str:
    return _composition_style(task_class)


def claim_family_for_task(task_class: NonLookupTaskClass, claim: str) -> str:
    return _claim_family_for_task(task_class, claim)


def empty_task_profile(task_class: NonLookupTaskClass) -> TaskChainProfile:
    return _empty_profile(task_class)


def profile_for_task(task_class: NonLookupTaskClass) -> IntentProfile:
    return _profile_for_task(task_class)
