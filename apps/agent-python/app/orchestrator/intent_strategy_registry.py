"""Intent → S5/S7/S8 strategy hints (no separate state graphs)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    IntentProfile,
    PrimaryIntent,
)
from app.schemas.s5_information_domain import InformationDomain

D = InformationDomain


class IntentStrategy(BaseModel):
    primary_intent: PrimaryIntent
    evidence_sensitivity: EvidenceSensitivity
    domain_priority: list[InformationDomain] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    partial_review_ok: bool = False
    single_platform_partial: bool = False
    refuse_asymmetric_comparison: bool = False
    stale_evidence_downgrade: bool = False
    forbid_model_prior_for_live: bool = False
    answer_style: AnswerStyle = AnswerStyle.ADVISORY
    compose_mode: str = "advisory"
    composition_policy_style: str = "advisory"


_INTENT_DOMAIN_PRIORITY: dict[PrimaryIntent, list[InformationDomain]] = {
    PrimaryIntent.LOOKUP: [
        D.OPERATION_STATUS,
        D.TICKET_BOOKING,
        D.GEO_RESOLUTION,
    ],
    PrimaryIntent.ADVISORY: [
        D.REVIEW_SIGNAL,
        D.SEASONALITY,
        D.ROUTE_PLANNING,
    ],
    PrimaryIntent.PLANNING: [
        D.ROUTE_PLANNING,
        D.REALTIME_STATUS,
        D.OPERATION_STATUS,
    ],
    PrimaryIntent.COMPARISON: [
        D.REVIEW_SIGNAL,
        D.TICKET_BOOKING,
        D.SEASONALITY,
        D.ROUTE_PLANNING,
    ],
    PrimaryIntent.REVIEW_CHECK: [D.REVIEW_SIGNAL],
    PrimaryIntent.REALTIME_CHECK: [
        D.REALTIME_STATUS,
        D.OPERATION_STATUS,
    ],
    PrimaryIntent.NEARBY: [
        D.NEARBY_RECOMMENDATION,
        D.REVIEW_SIGNAL,
    ],
    PrimaryIntent.CLARIFICATION: [D.GEO_RESOLUTION],
}

_INTENT_PREFERRED_TOOLS: dict[PrimaryIntent, list[str]] = {
    PrimaryIntent.LOOKUP: [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "search_mcp",
    ],
    PrimaryIntent.REVIEW_CHECK: [
        "ctrip_review_crawler_mcp",
        "dianping_review_crawler_mcp",
    ],
    PrimaryIntent.REALTIME_CHECK: [
        "baidu_weather_mcp",
        "openmeteo_mcp",
        "baidu_traffic_mcp",
        "crowd_estimation_mcp",
    ],
    PrimaryIntent.NEARBY: [
        "baidu_place_search_mcp",
        "dianping_nearby_crawler_mcp",
        "baidu_route_mcp",
    ],
    PrimaryIntent.PLANNING: [
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_traffic_mcp",
    ],
    PrimaryIntent.COMPARISON: [
        "ctrip_review_crawler_mcp",
        "dianping_review_crawler_mcp",
        "baidu_route_mcp",
        "baidu_route_matrix_mcp",
        "baidu_place_search_mcp",
        "search_mcp",
    ],
}

_DEFAULT_ANSWER_STYLE: dict[PrimaryIntent, AnswerStyle] = {
    PrimaryIntent.LOOKUP: AnswerStyle.DIRECT_FACT,
    PrimaryIntent.ADVISORY: AnswerStyle.ADVISORY,
    PrimaryIntent.PLANNING: AnswerStyle.ITINERARY,
    PrimaryIntent.COMPARISON: AnswerStyle.COMPARISON,
    PrimaryIntent.REVIEW_CHECK: AnswerStyle.ADVISORY,
    PrimaryIntent.REALTIME_CHECK: AnswerStyle.DIRECT_FACT,
    PrimaryIntent.NEARBY: AnswerStyle.RECOMMENDATION_LIST,
    PrimaryIntent.CLARIFICATION: AnswerStyle.CLARIFICATION,
}

_COMPOSE_MODE: dict[AnswerStyle, str] = {
    AnswerStyle.DIRECT_FACT: "fact_lookup",
    AnswerStyle.ADVISORY: "advisory",
    AnswerStyle.ITINERARY: "itinerary",
    AnswerStyle.COMPARISON: "compare",
    AnswerStyle.RECOMMENDATION_LIST: "nearby",
    AnswerStyle.CLARIFICATION: "clarification",
}

_COMPOSITION_POLICY_STYLE: dict[AnswerStyle, str] = {
    AnswerStyle.DIRECT_FACT: "direct",
    AnswerStyle.ADVISORY: "advisory",
    AnswerStyle.ITINERARY: "itinerary",
    AnswerStyle.COMPARISON: "comparison",
    AnswerStyle.RECOMMENDATION_LIST: "advisory",
    AnswerStyle.CLARIFICATION: "clarification",
}


def resolve_intent_strategy(profile: IntentProfile | None) -> IntentStrategy | None:
    if profile is None:
        return None
    primary = profile.primary_intent
    sensitivity = profile.evidence_sensitivity
    style = profile.answer_style or _DEFAULT_ANSWER_STYLE.get(primary, AnswerStyle.ADVISORY)

    partial_review = primary in {
        PrimaryIntent.ADVISORY,
        PrimaryIntent.REVIEW_CHECK,
        PrimaryIntent.COMPARISON,
    }
    single_platform = primary == PrimaryIntent.REVIEW_CHECK
    asymmetric = primary == PrimaryIntent.COMPARISON
    stale_downgrade = primary == PrimaryIntent.REALTIME_CHECK or sensitivity == EvidenceSensitivity.LIVE_REQUIRED
    forbid_prior_live = sensitivity == EvidenceSensitivity.LIVE_REQUIRED

    if sensitivity == EvidenceSensitivity.HARD_FACT:
        style = AnswerStyle.DIRECT_FACT

    return IntentStrategy(
        primary_intent=primary,
        evidence_sensitivity=sensitivity,
        domain_priority=list(_INTENT_DOMAIN_PRIORITY.get(primary, [])),
        preferred_tools=list(_INTENT_PREFERRED_TOOLS.get(primary, [])),
        partial_review_ok=partial_review,
        single_platform_partial=single_platform,
        refuse_asymmetric_comparison=asymmetric,
        stale_evidence_downgrade=stale_downgrade,
        forbid_model_prior_for_live=forbid_prior_live,
        answer_style=style,
        compose_mode=_COMPOSE_MODE.get(style, "advisory"),
        composition_policy_style=_COMPOSITION_POLICY_STYLE.get(style, "advisory"),
    )
