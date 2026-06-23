"""S5 information domain framework tests."""

from __future__ import annotations

import pytest

from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.s5_information_domain import InformationDomain
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.user_query import TravelAgentState


def _frame(**kwargs) -> SemanticFrame:
    base = dict(
        raw_query="",
        normalized_request="",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city=None, places=["可可托海"]),
        time_scope=TimeScope.CURRENT,
        information_needs=[],
        can_answer_with_model_prior=False,
    )
    base.update(kwargs)
    return SemanticFrame(**base)


def _contract(*claim_types: str, **claim_kwargs) -> ResponseContract:
    return ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type=ct, priority="required", **claim_kwargs)
            for ct in claim_types
        ]
    )


def test_domain_planner_ticket_price():
    contract = _contract("ticket_price", model_prior_allowed=False)
    plan = S5DomainPlanner().plan(contract, _frame(information_needs=["ticket_price"]))
    domain_values = {d.value for d in plan.domains}
    assert InformationDomain.GEO_RESOLUTION.value in domain_values
    assert InformationDomain.TICKET_BOOKING.value in domain_values


def test_domain_planner_best_time():
    contract = _contract("best_time_to_visit")
    plan = S5DomainPlanner().plan(contract, _frame(information_needs=["best_time_to_visit"]))
    domain_values = {d.value for d in plan.domains}
    assert InformationDomain.GEO_RESOLUTION.value in domain_values
    assert InformationDomain.SEASONALITY.value in domain_values


def test_domain_planner_route_plan():
    contract = _contract("route_plan")
    frame = _frame(
        decision_type=DecisionType.ROUTE_PLAN,
        information_needs=["route_plan", "transport_planning"],
    )
    plan = S5DomainPlanner().plan(contract, frame)
    domain_values = {d.value for d in plan.domains}
    assert InformationDomain.GEO_RESOLUTION.value in domain_values
    assert InformationDomain.ROUTE_PLANNING.value in domain_values


def test_domain_planner_review_signal():
    contract = _contract("value_for_money", "elderly_suitability")
    plan = S5DomainPlanner().plan(
        contract,
        _frame(
            task_family=TaskFamily.SUITABILITY,
            decision_type=DecisionType.WHETHER_TO_GO,
            information_needs=["value_for_money", "elderly_suitability"],
        ),
    )
    domain_values = {d.value for d in plan.domains}
    assert InformationDomain.REVIEW_SIGNAL.value in domain_values
    assert InformationDomain.GEO_RESOLUTION.value in domain_values


def test_domain_planner_nearby_food():
    contract = _contract("nearby_food")
    plan = S5DomainPlanner().plan(
        contract,
        _frame(
            decision_type=DecisionType.NEARBY_SEARCH,
            information_needs=["nearby_food"],
        ),
    )
    domain_values = {d.value for d in plan.domains}
    assert InformationDomain.NEARBY_RECOMMENDATION.value in domain_values
    assert InformationDomain.GEO_RESOLUTION.value in domain_values


def test_tool_whitelist_uses_domain_plan():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(
                claim_type="ticket_price",
                priority="required",
                preferred_tools=["search_mcp", "official_page_reader_mcp"],
                model_prior_allowed=False,
            )
        ]
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海景区票价如何")
    state.semantic_frame = _frame(information_needs=["ticket_price"])
    state.response_contract = contract
    wl = ToolWhitelistBuilder().build(state)
    assert state.s5_domain_plan is not None
    allowed = set(wl.allowed_tool_names())
    assert "search_mcp" in allowed or "search_mcp" in wl.blocked_tools
    assert wl.reason_by_tool.get("ctrip_ticket_crawler_mcp") in {
        "disabled_by_config",
        "not_implemented",
    }
    assert "dianping_ticket_crawler_mcp" in wl.blocked_tools


def test_placeholder_tools_blocked_not_called():
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="meituan_review_crawler_mcp",
        arguments={},
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    with pytest.raises(ValueError, match="not_implemented"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_geo_resolution_tools_are_prerequisite():
    contract = _contract("ticket_price")
    frame = _frame(entities=SemanticEntities(country="China", city=None, places=["云峰山"]))
    plan = S5DomainPlanner().plan(contract, frame)
    geo_tools = {
        b.tool_name
        for b in plan.tool_bindings
        if b.domain == InformationDomain.GEO_RESOLUTION and b.role.value != "forbidden"
    }
    assert "baidu_place_search_mcp" in geo_tools
    assert InformationDomain.GEO_RESOLUTION in plan.domains


def test_coverage_geo_does_not_cover_ticket_price():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="ticket_price", priority="required", model_prior_allowed=False),
        ]
    )
    geo_ev = Evidence(
        source_name="baidu_place_detail_mcp",
        source_type=SourceType.MAP,
        country="China",
        place_name="景区",
        claims=[
            Claim(claim_type=ClaimType.ADDRESS, value="某地址", confidence=0.7),
            Claim(claim_type=ClaimType.PRICE_CANDIDATE, value="约80元", confidence=0.5),
        ],
    )
    report = EvidenceCoverageChecker().check(contract, [geo_ev], [])
    item = report.items[0]
    assert item.covered is False
    assert item.coverage_quality in ("partial", "none")


def test_realtime_weather_not_cover_long_term_seasonality():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="best_time_to_visit", priority="required"),
        ]
    )
    weather_ev = Evidence(
        source_name="openmeteo_mcp",
        source_type=SourceType.WEATHER_API,
        country="China",
        claims=[Claim(claim_type=ClaimType.WEATHER, value="晴 25°C", confidence=0.8)],
    )
    report = EvidenceCoverageChecker().check(contract, [weather_ev], [])
    item = report.items[0]
    assert item.covered is False


def test_need_tool_profiles_prioritize_official_for_hard_facts():
    from app.tools.mcp.tool_specs import NEED_TOOL_PROFILES

    ticket = NEED_TOOL_PROFILES["ticket_price"]
    assert ticket[0] == "official_page_reader_mcp"
    assert ticket.index("official_page_reader_mcp") < ticket.index("ctrip_ticket_signal_crawler_mcp")

    hours = NEED_TOOL_PROFILES["opening_hours"]
    assert hours[0] == "official_page_reader_mcp"
