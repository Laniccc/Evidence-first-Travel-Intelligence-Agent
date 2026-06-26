"""Regression tests for height_elevation → elevation lookup chain fixes."""

from __future__ import annotations

from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.lookup_entity_resolution_policy import (
    count_entity_resolution_calls,
    entity_resolution_allowed_for_lookup,
    lookup_entity_anchor_satisfied,
)
from app.orchestrator.lookup_need_aliases import resolve_lookup_need
from app.orchestrator.peak_elevation_extraction import (
    discover_peak_names_from_evidence,
    elevation_needs_peak_gap,
    extract_peak_elevation_table,
)
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.schemas.coverage_report import CoverageItem
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.s5_information_domain import InformationDomain
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.tool_trace import ToolTrace
from app.schemas.user_query import TravelAgentState


def _huangshan_elevation_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="黄山海拔多少米？",
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="黄山市", places=["黄山"]),
        information_needs=["height_elevation"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=["height_elevation"],
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def test_height_elevation_maps_to_elevation_claim():
    state = _huangshan_elevation_state()
    claim_types = [c.claim_type for c in state.response_contract.claim_requirements]
    assert "elevation" in claim_types
    assert "general_travel_advice" not in claim_types
    elev = next(c for c in state.response_contract.claim_requirements if c.claim_type == "elevation")
    assert elev.claim_family == "geo_fact"
    assert elev.model_prior_allowed is False
    assert elev.requires_exact_fact is True
    assert "wikidata_mcp" in elev.preferred_tools


def test_resolve_lookup_need_alias():
    assert resolve_lookup_need("height_elevation") == "elevation"


def test_elevation_domain_includes_geo_fact_tools():
    state = _huangshan_elevation_state()
    plan = S5DomainPlanner().plan(
        state.response_contract,
        state.semantic_frame,
        intent_profile=state.intent_profile,
        intent_strategy=state.intent_strategy,
    )
    assert InformationDomain.GEO_FACT in plan.domains
    assert InformationDomain.GEO_RESOLUTION in plan.domains
    tool_names = {b.tool_name for b in plan.tool_bindings}
    assert "wikidata_mcp" in tool_names
    assert "wikipedia_mcp" in tool_names
    assert "ctrip_ticket_signal_crawler_mcp" not in tool_names


def test_entity_resolution_stops_after_anchor():
    state = _huangshan_elevation_state()
    state.semantic_frame.entities.city = ""
    assert entity_resolution_allowed_for_lookup(state)
    state.structured_result = {
        "fact_anchor": {"resolved_name": "黄山风景区", "city": "黄山市", "confidence": 0.85},
        "subagent_results": [{"subagent": "entity_resolution_agent"}],
    }
    assert lookup_entity_anchor_satisfied(state)
    assert not entity_resolution_allowed_for_lookup(state)
    state.structured_result["subagent_results"] = [
        {"subagent": "entity_resolution_agent"},
        {"subagent": "entity_resolution_agent"},
    ]
    assert count_entity_resolution_calls(state) == 2
    state.structured_result.pop("fact_anchor")
    assert not entity_resolution_allowed_for_lookup(state)


def test_s5_finish_not_blocked_by_unattempted_optional_tools():
    contract = ResponseContract(
        user_goal_summary="黄山海拔",
        claim_requirements=[
            ClaimRequirement(
                claim_type="elevation",
                claim_family="geo_fact",
                priority="required",
                requires_exact_fact=True,
                preferred_tools=[
                    "wikidata_mcp",
                    "wikipedia_mcp",
                    "search_mcp",
                    "osm_mcp",
                    "fallback",
                ],
                model_prior_allowed=False,
            )
        ],
    )
    traces = [
        ToolTrace(tool_name="search_mcp", status="ok"),
        ToolTrace(tool_name="fact_lookup_agent", status="ok"),
    ]
    items = [
        CoverageItem(
            claim_type="elevation",
            covered=False,
            coverage_quality="none",
            can_answer=False,
            missing_behavior="answer_with_limitation",
        )
    ]
    untried = EvidenceCoverageChecker._untried_required_primary_tools(contract, traces, items)
    assert "fallback" not in untried
    assert "osm_mcp" not in untried


def test_elevation_claim_can_be_curated_from_search_evidence():
    contract = ResponseContract(
        user_goal_summary="黄山海拔",
        claim_requirements=[
            ClaimRequirement(
                claim_type="elevation",
                claim_family="geo_fact",
                priority="required",
                requires_exact_fact=True,
                model_prior_allowed=False,
            )
        ],
    )
    evidence = [
        Evidence(
            evidence_id="ev-elev",
            source_name="search_mcp",
            source_type=SourceType.WEB,
            country="China",
            place_name="黄山",
            claims=[
                Claim(
                    claim_type=ClaimType.GENERAL_FACT,
                    value="黄山风景区主峰莲花峰海拔1864米",
                    confidence=0.7,
                )
            ],
            confidence=0.7,
        )
    ]
    report = EvidenceCoverageChecker().check(contract, evidence, [])
    elev_item = next(i for i in report.items if i.claim_type == "elevation")
    assert elev_item.coverage_quality in {"partial", "strong"}
    assert elev_item.covered


def test_elevation_subclaims_in_contract():
    state = _huangshan_elevation_state()
    types = {c.claim_type for c in state.response_contract.claim_requirements}
    assert "highest_peak_elevation" in types
    assert "main_peak_elevations" in types


def test_elevation_range_only_triggers_peak_gap():
    evidence = [
        Evidence(
            evidence_id="ev-range",
            source_name="search_mcp",
            source_type=SourceType.WEB,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.GENERAL_FACT,
                    value="莲花、光明顶、天都为黄山三大主峰，海拔均逾1800米",
                    confidence=0.6,
                )
            ],
            confidence=0.6,
        )
    ]
    table = extract_peak_elevation_table(evidence, place_name="黄山")
    assert table.value_granularity == "range_only"
    assert elevation_needs_peak_gap(table, exact_required=True)
    peaks = discover_peak_names_from_evidence(evidence)
    assert len(peaks) >= 2


def test_peak_elevation_extraction_lotus_bright_tiandu():
    evidence = [
        Evidence(
            evidence_id="ev-peaks",
            source_name="wikipedia_mcp",
            source_type=SourceType.WEB,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.GENERAL_FACT,
                    value="莲花峰海拔1864米，光明顶海拔1860米，天都峰海拔1810米",
                    confidence=0.8,
                )
            ],
            confidence=0.8,
        )
    ]
    table = extract_peak_elevation_table(evidence, place_name="黄山")
    assert table.value_granularity == "exact_numeric"
    assert len(table.peaks) >= 3


def test_geo_fact_whitelist_excludes_ticket_review_tools():
    from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder, _contract_is_geo_fact_elevation

    state = _huangshan_elevation_state()
    assert _contract_is_geo_fact_elevation(state.response_contract)
    wl = ToolWhitelistBuilder().build(state)
    allowed = set(wl.allowed_tool_names())
    assert "dianping_ticket_signal_crawler_mcp" not in allowed
    assert "ticket_price_history_query" not in allowed


def test_s8_elevation_answer_includes_peak_table_when_available():
    from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft

    state = _huangshan_elevation_state()
    state.evidence = [
        Evidence(
            evidence_id="ev1",
            source_name="wiki",
            source_type=SourceType.WEB,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.ELEVATION,
                    value="莲花峰海拔1864米",
                    confidence=0.8,
                )
            ],
            confidence=0.8,
        )
    ]
    draft = build_fact_lookup_draft(state)
    text = draft.render_text()
    assert "1864" in text
    assert "莲花" in text


def test_official_source_discovery_skips_without_urls():
    from app.agents.fact_lookup_phase_runner import _has_url_inputs

    state = _huangshan_elevation_state()
    assert not _has_url_inputs(state)
    state.evidence = [
        Evidence(
            evidence_id="ev-url",
            source_name="search",
            source_type=SourceType.WEB,
            country="China",
            source_url="https://example.com/huangshan",
            confidence=0.5,
        )
    ]
    assert _has_url_inputs(state)
