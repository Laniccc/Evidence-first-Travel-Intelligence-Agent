"""Intent → S5/S7/S8 strategy registry (PrimaryIntent does not replace ResponseContract)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.intent_profile import (
    AnswerStyle,
    EvidenceSensitivity,
    IntentProfile,
    PrimaryIntent,
)
from app.schemas.s5_information_domain import InformationDomain

D = InformationDomain

S7PolicyName = Literal[
    "hard_fact_strict",
    "freshness_strict",
    "poi_quality_filter",
    "aligned_dimension_comparison",
    "review_signal_adoption",
    "route_feasibility",
    "open_claim_advisory",
    "clarification_decision",
]

RetrievalMode = Literal[
    "minimal_probe",
    "single_claim_strict",
    "strict_fact_lookup",
    "poi_recommendation",
    "live_status",
    "multi_place_parallel",
    "route_first",
    "review_first",
    "mixed_advisory",
]


class IntentToolTiers(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    fallback: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class IntentStrategyTemplate(BaseModel):
    retrieval_mode: RetrievalMode = "mixed_advisory"
    s7_policy: S7PolicyName = "open_claim_advisory"
    domain_priority: list[InformationDomain] = Field(default_factory=list)
    tool_tiers: IntentToolTiers = Field(default_factory=IntentToolTiers)
    preferred_subagents: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    skip_s5: bool = False
    compose_mode: str = "advisory"
    composition_policy_style: str = "advisory"
    default_answer_style: AnswerStyle = AnswerStyle.ADVISORY
    partial_review_ok: bool = False
    single_platform_partial: bool = False
    refuse_asymmetric_comparison: bool = False
    stale_evidence_downgrade: bool = False
    forbid_model_prior_for_live: bool = False
    state_chain_hint: str = ""


class IntentStrategy(BaseModel):
    primary_intent: PrimaryIntent
    evidence_sensitivity: EvidenceSensitivity
    retrieval_mode: RetrievalMode = "mixed_advisory"
    s7_policy: S7PolicyName = "open_claim_advisory"
    domain_priority: list[InformationDomain] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    tool_tiers: IntentToolTiers = Field(default_factory=IntentToolTiers)
    preferred_subagents: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    skip_s5: bool = False
    partial_review_ok: bool = False
    single_platform_partial: bool = False
    refuse_asymmetric_comparison: bool = False
    stale_evidence_downgrade: bool = False
    forbid_model_prior_for_live: bool = False
    answer_style: AnswerStyle = AnswerStyle.ADVISORY
    compose_mode: str = "advisory"
    composition_policy_style: str = "advisory"
    state_chain_hint: str = ""


_GEO_TOOLS = [
    "baidu_place_search_mcp",
    "baidu_place_detail_mcp",
    "baidu_geocode_mcp",
    "baidu_reverse_geocode_mcp",
    "osm_mcp",
    "wikidata_mcp",
    "wikipedia_mcp",
]

_OFFICIAL_TOOLS = [
    "official_source_discovery_mcp",
    "official_page_reader_mcp",
    "search_mcp",
    "browser_mcp",
    "government_notice_search_mcp",
    "tourism_board_page_reader_mcp",
]

_TICKET_TOOLS = [
    "official_page_reader_mcp",
    "official_source_discovery_mcp",
    "search_mcp",
    "browser_mcp",
    "ticketlens_experience_mcp",
    "fliggy_ticket_api_mcp",
    "fliggy_ticket_snapshot_crawler_mcp",
    "ctrip_ticket_signal_crawler_mcp",
    "dianping_ticket_signal_crawler_mcp",
]

_NEARBY_TOOLS = [
    "baidu_place_search_mcp",
    "baidu_place_detail_mcp",
    "baidu_reverse_geocode_mcp",
    "baidu_route_mcp",
    "dianping_nearby_crawler_mcp",
    "meituan_nearby_crawler_mcp",
    "dianping_review_crawler_mcp",
    "ctrip_review_crawler_mcp",
    "review_signal_mcp",
    "search_mcp",
    "browser_mcp",
]

_REVIEW_TOOLS = [
    "review_signal_mcp",
    "dianping_review_crawler_mcp",
    "ctrip_review_crawler_mcp",
    "public_review_search_mcp",
    "search_mcp",
    "browser_mcp",
]

_ROUTE_TOOLS = [
    "baidu_route_mcp",
    "baidu_route_matrix_mcp",
    "baidu_traffic_mcp",
    "baidu_geocode_mcp",
    "baidu_place_search_mcp",
]

_WEATHER_TOOLS = [
    "baidu_weather_mcp",
    "openmeteo_mcp",
    "weather_mcp",
    "weather",
]

INTENT_STRATEGY_REGISTRY: dict[PrimaryIntent, IntentStrategyTemplate] = {
    PrimaryIntent.CLARIFICATION: IntentStrategyTemplate(
        retrieval_mode="minimal_probe",
        s7_policy="clarification_decision",
        domain_priority=[D.GEO_RESOLUTION],
        tool_tiers=IntentToolTiers(
            primary=["baidu_place_search_mcp", "baidu_geocode_mcp"],
            fallback=["search_mcp", "wikidata_mcp", "osm_mcp"],
            forbidden=[
                "ticketlens_experience_mcp",
                "fliggy_ticket_api_mcp",
    "fliggy_ticket_snapshot_crawler_mcp",
                "ctrip_ticket_signal_crawler_mcp",
                "dianping_ticket_signal_crawler_mcp",
                "dianping_review_crawler_mcp",
                "ctrip_review_crawler_mcp",
                "baidu_route_mcp",
                "baidu_weather_mcp",
                "knowledge_prior",
            ],
        ),
        preferred_subagents=["entity_resolution_agent"],
        forbidden_tools=["knowledge_prior"],
        skip_s5=True,
        compose_mode="clarification",
        composition_policy_style="clarification",
        default_answer_style=AnswerStyle.CLARIFICATION,
        state_chain_hint="S3 clarification → S8; optional S5 entity_probe for place_disambiguation",
    ),
    PrimaryIntent.LOOKUP: IntentStrategyTemplate(
        retrieval_mode="strict_fact_lookup",
        s7_policy="hard_fact_strict",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.GEO_FACT,
            D.OPERATION_STATUS,
            D.TICKET_BOOKING,
        ],
        tool_tiers=IntentToolTiers(
            primary=[*_GEO_TOOLS[:4], *_OFFICIAL_TOOLS[:4]],
            secondary=_TICKET_TOOLS[4:],
            fallback=["osm_mcp", "wikidata_mcp", "wikipedia_mcp", "search_mcp"],
            forbidden=["knowledge_prior"],
        ),
        preferred_subagents=[
            "fact_lookup_agent",
            "entity_resolution_agent",
            "fact_search_agent",
            "evidence_contradiction_decomposer_agent",
        ],
        forbidden_tools=["knowledge_prior"],
        compose_mode="fact_lookup",
        composition_policy_style="direct",
        default_answer_style=AnswerStyle.DIRECT_FACT,
        state_chain_hint="geo → official → ticket/operation → S7 hard_fact_strict",
    ),
    PrimaryIntent.NEARBY: IntentStrategyTemplate(
        retrieval_mode="poi_recommendation",
        s7_policy="poi_quality_filter",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.NEARBY_RECOMMENDATION,
            D.ROUTE_PLANNING,
            D.REVIEW_SIGNAL,
        ],
        tool_tiers=IntentToolTiers(
            primary=_NEARBY_TOOLS,
            fallback=["search_mcp", "browser_mcp", "restaurant", "lodging"],
            forbidden=["knowledge_prior"],
        ),
        preferred_subagents=["entity_resolution_agent"],
        forbidden_tools=["knowledge_prior"],
        compose_mode="nearby",
        composition_policy_style="advisory",
        default_answer_style=AnswerStyle.RECOMMENDATION_LIST,
        partial_review_ok=True,
        state_chain_hint="geo anchor → per-candidate nearby retrieval → S8 area-guided compose",
    ),
    PrimaryIntent.REALTIME_CHECK: IntentStrategyTemplate(
        retrieval_mode="live_status",
        s7_policy="freshness_strict",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.REALTIME_STATUS,
            D.OPERATION_STATUS,
            D.ROUTE_PLANNING,
        ],
        tool_tiers=IntentToolTiers(
            primary=[
                *_WEATHER_TOOLS,
                "baidu_traffic_mcp",
                "baidu_route_mcp",
                *_OFFICIAL_TOOLS[:4],
                "crowd_estimation_mcp",
                "event_calendar_mcp",
                "holiday_calendar_mcp",
                "review_signal_mcp",
                "dianping_review_crawler_mcp",
                "ctrip_review_crawler_mcp",
            ],
            forbidden=["knowledge_prior"],
        ),
        preferred_subagents=[
            "entity_resolution_agent",
            "weather_context_agent",
            "fact_search_agent",
        ],
        forbidden_tools=["knowledge_prior"],
        compose_mode="realtime_status",
        composition_policy_style="direct",
        default_answer_style=AnswerStyle.DIRECT_FACT,
        stale_evidence_downgrade=True,
        forbid_model_prior_for_live=True,
        state_chain_hint="geo → weather/traffic/notice → S7 freshness_strict",
    ),
    PrimaryIntent.COMPARISON: IntentStrategyTemplate(
        retrieval_mode="multi_place_parallel",
        s7_policy="aligned_dimension_comparison",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.REVIEW_SIGNAL,
            D.ROUTE_PLANNING,
            D.TICKET_BOOKING,
            D.SEASONALITY,
        ],
        tool_tiers=IntentToolTiers(
            primary=[
                *_GEO_TOOLS[:3],
                *_REVIEW_TOOLS,
                "baidu_route_mcp",
                "baidu_route_matrix_mcp",
                *_OFFICIAL_TOOLS[:2],
                *_TICKET_TOOLS[4:6],
                "climate_mcp",
                "openmeteo_mcp",
                "seasonality",
            ],
            fallback=["search_mcp", "knowledge_prior"],
        ),
        preferred_subagents=[
            "entity_resolution_agent",
            "fact_search_agent",
            "route_feasibility_agent",
        ],
        compose_mode="compare",
        composition_policy_style="comparison",
        default_answer_style=AnswerStyle.COMPARISON,
        partial_review_ok=True,
        refuse_asymmetric_comparison=True,
        state_chain_hint="per-place geo → review → route → S7 aligned comparison",
    ),
    PrimaryIntent.PLANNING: IntentStrategyTemplate(
        retrieval_mode="route_first",
        s7_policy="route_feasibility",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.ROUTE_PLANNING,
            D.REALTIME_STATUS,
            D.OPERATION_STATUS,
            D.REVIEW_SIGNAL,
        ],
        tool_tiers=IntentToolTiers(
            primary=[
                *_ROUTE_TOOLS,
                *_OFFICIAL_TOOLS[:4],
                "baidu_place_detail_mcp",
                *_WEATHER_TOOLS[:2],
                *_REVIEW_TOOLS[:3],
            ],
            secondary=[
                "itinerary_planner_mcp",
                "route_feasibility_checker_mcp",
                "elderly_friendly_route_scorer_mcp",
                "family_trip_planner_mcp",
                "walking_intensity_estimator_mcp",
                "time_budget_planner_mcp",
            ],
            fallback=["search_mcp", "browser_mcp"],
        ),
        preferred_subagents=[
            "entity_resolution_agent",
            "route_feasibility_agent",
            "weather_context_agent",
        ],
        compose_mode="itinerary",
        composition_policy_style="itinerary",
        default_answer_style=AnswerStyle.ITINERARY,
        partial_review_ok=True,
        state_chain_hint="geo → route_matrix → traffic/weather → opening_hours",
    ),
    PrimaryIntent.REVIEW_CHECK: IntentStrategyTemplate(
        retrieval_mode="review_first",
        s7_policy="review_signal_adoption",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.REVIEW_SIGNAL,
        ],
        tool_tiers=IntentToolTiers(
            primary=[
                *_REVIEW_TOOLS,
                "mafengwo_note_crawler_mcp",
                "xiaohongshu_note_crawler_mcp",
                "tripadvisor_review_crawler_mcp",
                "ticketlens_experience_mcp",
            ],
            fallback=["baidu_place_detail_mcp", "search_mcp", "browser_mcp"],
        ),
        preferred_subagents=["entity_resolution_agent", "fact_search_agent"],
        compose_mode="review_insight",
        composition_policy_style="advisory",
        default_answer_style=AnswerStyle.ADVISORY,
        partial_review_ok=True,
        single_platform_partial=True,
        state_chain_hint="geo → review_signal → platform crawlers",
    ),
    PrimaryIntent.ADVISORY: IntentStrategyTemplate(
        retrieval_mode="mixed_advisory",
        s7_policy="open_claim_advisory",
        domain_priority=[
            D.GEO_RESOLUTION,
            D.REVIEW_SIGNAL,
            D.SEASONALITY,
            D.ROUTE_PLANNING,
            D.REALTIME_STATUS,
            D.OPERATION_STATUS,
        ],
        tool_tiers=IntentToolTiers(
            primary=[
                *_REVIEW_TOOLS,
                "search_mcp",
                "browser_mcp",
                "climate_mcp",
                "openmeteo_mcp",
                "seasonality",
                "baidu_route_mcp",
                "baidu_route_matrix_mcp",
                "baidu_place_detail_mcp",
                *_OFFICIAL_TOOLS[:2],
            ],
            fallback=["knowledge_prior"],
        ),
        preferred_subagents=[
            "entity_resolution_agent",
            "fact_search_agent",
            "route_feasibility_agent",
            "weather_context_agent",
        ],
        compose_mode="advisory",
        composition_policy_style="advisory",
        default_answer_style=AnswerStyle.ADVISORY,
        partial_review_ok=True,
        state_chain_hint="geo → review → seasonality/route → prior fallback",
    ),
}


def resolve_intent_strategy(profile: IntentProfile | None) -> IntentStrategy | None:
    if profile is None:
        return None
    primary = profile.primary_intent
    sensitivity = profile.evidence_sensitivity
    template = INTENT_STRATEGY_REGISTRY.get(primary)
    if template is None:
        return None

    style = profile.answer_style or template.default_answer_style
    if sensitivity == EvidenceSensitivity.HARD_FACT:
        style = AnswerStyle.DIRECT_FACT
    elif sensitivity == EvidenceSensitivity.LIVE_REQUIRED:
        style = AnswerStyle.DIRECT_FACT

    compose_mode = template.compose_mode

    preferred_tools = list(
        dict.fromkeys(
            template.tool_tiers.primary
            + template.tool_tiers.secondary
            + template.tool_tiers.fallback
        )
    )

    partial_review = template.partial_review_ok or primary in {
        PrimaryIntent.ADVISORY,
        PrimaryIntent.REVIEW_CHECK,
        PrimaryIntent.COMPARISON,
        PrimaryIntent.NEARBY,
        PrimaryIntent.PLANNING,
    }
    stale_downgrade = template.stale_evidence_downgrade or sensitivity == EvidenceSensitivity.LIVE_REQUIRED
    forbid_prior_live = template.forbid_model_prior_for_live or sensitivity == EvidenceSensitivity.LIVE_REQUIRED

    return IntentStrategy(
        primary_intent=primary,
        evidence_sensitivity=sensitivity,
        retrieval_mode=template.retrieval_mode,
        s7_policy=template.s7_policy,
        domain_priority=list(template.domain_priority),
        preferred_tools=preferred_tools,
        tool_tiers=template.tool_tiers,
        preferred_subagents=list(template.preferred_subagents),
        forbidden_tools=list(template.forbidden_tools),
        skip_s5=template.skip_s5,
        partial_review_ok=partial_review,
        single_platform_partial=template.single_platform_partial,
        refuse_asymmetric_comparison=template.refuse_asymmetric_comparison,
        stale_evidence_downgrade=stale_downgrade,
        forbid_model_prior_for_live=forbid_prior_live,
        answer_style=style,
        compose_mode=compose_mode,
        composition_policy_style=template.composition_policy_style,
        state_chain_hint=template.state_chain_hint,
    )
