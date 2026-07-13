"""Evidence-side S7 policy for non-lookup travel tasks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from app.evidence.evidence_decision_report import ClaimDecision, EvidenceDecisionReport
from app.evidence.evidence_evaluator import evaluate_evidence
from app.evidence.evidence_model import ClaimType, DataFreshness, Evidence, SourceType


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

class NearbyCandidate:
    evidence_id: str
    name: str
    category: str
    distance_m: int | None
    reason: str
    accepted: bool

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

def _as_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).replace("m", "").strip()))
    except (TypeError, ValueError):
        return None

def evaluate_non_lookup_task_evidence(
    state: TravelAgentState,
    *,
    profile: Any,
    target_label: str,
    clarification_question: str,
    related_poi: bool,
) -> EvidenceDecisionReport:
    """Evaluate an already-classified task without resolving cross-layer state."""
    if profile.task_class == "clarification":
        report = _clarification_report(clarification_question, related_poi)
    else:
        report = evaluate_evidence(state, target_label=target_label)
        _apply_task_s7_policy(state, profile, report)
    state.evidence_decision_report = report
    return report


def build_non_lookup_task_debug_trace(
    state: TravelAgentState,
    *,
    profile: Any,
    report: EvidenceDecisionReport | None = None,
) -> TaskDebugTrace:
    """Build S7 observability data from an explicit task profile and report."""
    report = report or state.evidence_decision_report
    claim_rows: list[dict] = []
    adoption_levels: dict[str, str] = {}
    if report:
        for decision in report.claim_decisions:
            claim_rows.append(decision.model_dump(mode="json"))
            adoption_levels[decision.claim_type] = (
                decision.adoption_level or _adoption_level_from_decision(decision)
            )

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
        skipped_with_reason=_skipped_tools(state, profile),
        evidence_count_by_family=_evidence_count_by_family(state.evidence),
        claim_decisions=claim_rows,
        adoption_levels=adoption_levels,
        user_visible_limitations=list(dict.fromkeys(state.user_visible_limitations + state.limitations)),
        internal_debug_limitations=list(dict.fromkeys(state.internal_debug_limitations)),
    )


def _clarification_report(question: str, related_poi: bool) -> EvidenceDecisionReport:
    if related_poi:
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


def _selected_state_path(state: TravelAgentState, profile: Any) -> list[str]:
    if profile.task_class == "clarification":
        return [step for step in profile.task_chain if step != "S4 RegionGate"]
    if state.evidence_decision_report and state.evidence_decision_report.evidence_gap_requests:
        return profile.task_chain
    return [step for step in profile.task_chain if step != "Optional GapFill"]
