"""Intent-aware S7 adoption policy dispatch."""

from __future__ import annotations

from app.orchestrator.claim_policy_registry import ClaimPolicyView
from app.orchestrator.intent_strategy_registry import IntentStrategy, S7PolicyName

_NEARBY_CLAIMS = frozenset(
    {
        "nearby_food",
        "nearby_poi",
        "nearby_hotel",
        "nearby_rest_area",
        "nearby_parking",
        "nearby_toilet",
        "nearby_station",
        "nearby_dining",
        "nearby_restaurant",
        "nearby_lodging",
        "nearby_attraction",
    }
)

_REVIEW_CLAIMS = frozenset(
    {
        "review_summary",
        "value_for_money",
        "crowd_risk",
        "queue_risk",
        "commercialization_risk",
        "transport_difficulty",
        "photo_value",
        "family_friendly",
        "elderly_suitability",
        "crowd_level",
    }
)

_LIVE_CLAIMS = frozenset(
    {
        "weather_today",
        "today_weather",
        "current_weather",
        "forecast",
        "weather",
        "traffic_status",
        "congestion_risk",
        "road_traffic",
        "current_crowd",
        "current_crowd_estimate",
        "queue_time",
    }
)

_HARD_FACT_CLAIMS = frozenset(
    {
        "ticket_price",
        "opening_hours",
        "temporary_closure",
        "reservation_policy",
        "seasonal_operation_status",
        "road_opening_period",
    }
)


def apply_intent_s7_policy(
    s7_policy: S7PolicyName | str,
    policy: ClaimPolicyView,
    quality: str,
    adoption: str,
    *,
    intent_strategy: IntentStrategy | None = None,
) -> str:
    """Adjust adoption decision based on intent-level S7 policy."""
    claim = policy.claim_type

    if s7_policy == "hard_fact_strict":
        if claim in _HARD_FACT_CLAIMS:
            if quality == "weak":
                return "adopt_with_limitation"
            if quality == "none" and policy.requires_exact_fact:
                return "refuse_to_guess"
        return adoption

    if s7_policy == "freshness_strict":
        if claim in _LIVE_CLAIMS:
            if quality in {"none", "weak"}:
                return "refuse_to_guess" if policy.requires_live_data else "adopt_with_limitation"
            if intent_strategy and intent_strategy.stale_evidence_downgrade and quality == "partial":
                return "adopt_with_limitation"
        return adoption

    if s7_policy == "poi_quality_filter":
        if claim in _NEARBY_CLAIMS:
            if quality == "none":
                return "refuse_to_guess"
            if quality == "weak":
                return "adopt_with_limitation"
            if quality == "partial":
                return "adopt_with_limitation"
        return adoption

    if s7_policy == "aligned_dimension_comparison":
        if quality == "none" and intent_strategy and intent_strategy.refuse_asymmetric_comparison:
            return "refuse_to_guess"
        if quality == "weak":
            return "adopt_with_limitation"
        return adoption

    if s7_policy == "review_signal_adoption":
        if claim in _REVIEW_CLAIMS:
            if quality == "none":
                return "refuse_to_guess"
            if quality == "weak":
                return "adopt_with_limitation"
        if claim in _HARD_FACT_CLAIMS or claim in _LIVE_CLAIMS:
            if quality in {"weak", "none"}:
                return "refuse_to_guess"
        return adoption

    if s7_policy == "route_feasibility":
        if claim in {"route_plan", "itinerary_feasibility", "distance", "duration", "transit"}:
            if quality == "none":
                return "adopt_with_limitation"
        return adoption

    if s7_policy == "open_claim_advisory":
        if quality == "none" and not policy.model_prior_allowed:
            return "refuse_to_guess"
        if quality == "none" and policy.model_prior_allowed:
            return "adopt_with_limitation"
        return adoption

    if s7_policy == "clarification_decision":
        if claim in {"entity_resolution", "place_lookup", "disambiguation"}:
            return adoption if quality != "none" else "ask_clarification"
        return "omit"

    return adoption
