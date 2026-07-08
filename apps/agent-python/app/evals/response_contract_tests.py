"""ResponseContract + coverage integration tests."""

from __future__ import annotations

import pytest

from app.agents.answer_composer_agent import AnswerComposerAgent
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.information_need import InformationNeed, InformationNeedType, NeedPriority
from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.semantic_frame import (
    AnswerMode,
    AnswerModeDecision,
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.place_ambiguity import PlaceAmbiguityCandidate, PlaceAmbiguityInfo
from app.schemas.tool_trace import ToolTrace
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.user_query import TravelAgentState


def _frame(**kwargs) -> SemanticFrame:
    base = dict(
        raw_query="",
        normalized_request="",
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.ADVISORY,
        decision_type=DecisionType.BEST_TIME_TO_VISIT,
        entities=SemanticEntities(country="China", city=None, places=["云峰山"]),
        time_scope=TimeScope.SEASONAL,
        information_needs=["best_time_to_visit"],
        can_answer_with_model_prior=True,
    )
    base.update(kwargs)
    return SemanticFrame(**base)


def test_response_contract_for_ticket_price():
    frame = _frame(
        raw_query="禾木景区票价如何",
        decision_type=DecisionType.FACT_LOOKUP,
        task_family=TaskFamily.FACT_LOOKUP,
        information_needs=["ticket_price"],
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )
    contract = ResponseContractCompiler().compile(frame)
    ticket = next(c for c in contract.claim_requirements if c.claim_type == "ticket_price")
    assert ticket.priority == "required"
    assert ticket.requires_exact_fact is True
    assert ticket.model_prior_allowed is False
    assert "knowledge_prior" in ticket.forbidden_tools


def test_response_contract_for_best_time():
    frame = _frame(
        raw_query="云峰山什么时候去游玩比较合适",
        entities=SemanticEntities(country="China", city=None, places=["云峰山"]),
        information_needs=["best_time_to_visit"],
    )
    contract = ResponseContractCompiler().compile(frame)
    bt = next(c for c in contract.claim_requirements if c.claim_type == "best_time_to_visit")
    assert bt.model_prior_allowed is True
    tools = set(bt.preferred_tools)
    assert "baidu_place_search_mcp" in tools
    assert "search_mcp" in tools
    assert "seasonality" in tools
    assert contract.entity_policy.requires_disambiguation is False
    assert contract.clarification_policy.should_ask is False
    assert "云峰山" in contract.gated_search_keywords


def test_response_contract_for_duku_opening_month():
    frame = _frame(
        raw_query="独库公路每年几月份开放",
        normalized_request="独库公路开放月份",
        entities=SemanticEntities(country="China", city=None, places=["独库公路"]),
        information_needs=["best_time_to_visit", "seasonality"],
    )
    contract = ResponseContractCompiler().compile(frame)
    seasonal = next(c for c in contract.claim_requirements if c.claim_type == "seasonal_operation_status")
    assert seasonal.priority == "required"
    assert seasonal.model_prior_allowed is False
    assert "search_mcp" in seasonal.preferred_tools
    assert "official_page_reader_mcp" in seasonal.preferred_tools
    assert "baidu_place_search_mcp" in seasonal.preferred_tools
    optional = [c for c in contract.claim_requirements if c.claim_type == "general_seasonal_context"]
    assert optional and optional[0].model_prior_allowed is True


def test_s5_uses_response_contract_before_old_information_needs():
    frame = _frame(information_needs=["best_time_to_visit"])
    contract = ResponseContractCompiler().compile(frame)
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    state.semantic_frame = frame
    state.response_contract = contract
    state.information_needs = [
        InformationNeed(need_type=InformationNeedType.WEATHER, priority=NeedPriority.HIGH)
    ]
    wl = ToolWhitelistBuilder().build(state)
    names = set(wl.allowed_tool_names())
    assert "knowledge_prior" in names or "knowledge_prior" in wl.blocked_tools
    assert "knowledge_prior" not in wl.reason_by_tool or "weather" not in str(wl.policy_notes)


def test_coverage_rejects_irrelevant_fallback_crowd():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="ticket_price", priority="required", model_prior_allowed=False),
        ]
    )
    crowd_ev = Evidence(
        source_name="reviews",
        source_type=SourceType.REVIEW_PLATFORM,
        country="China",
        claims=[Claim(claim_type=ClaimType.CROWD, value="busy", confidence=0.7)],
    )
    report = EvidenceCoverageChecker().check(contract, [crowd_ev], [])
    item = report.items[0]
    assert item.covered is False
    assert item.coverage_quality == "none"


def test_coverage_rejects_generic_seasonality_template():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="best_time_to_visit", priority="required", model_prior_allowed=True),
        ]
    )
    weak_ev = Evidence(
        source_name="seasonality",
        source_type=SourceType.WEB,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value="建议查阅旅游局或气候资料",
                confidence=0.6,
            )
        ],
    )
    report = EvidenceCoverageChecker().check(contract, [weak_ev], [])
    assert report.items[0].coverage_quality in ("none", "weak")
    assert report.all_required_covered is False


def test_ticket_price_cannot_finish_if_search_available_untried():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(
                claim_type="ticket_price",
                priority="required",
                preferred_tools=["search_mcp", "official_page_reader_mcp"],
                forbidden_tools=["knowledge_prior"],
                model_prior_allowed=False,
            )
        ]
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="票价")
    state.response_contract = contract
    state.semantic_frame = _frame(information_needs=["ticket_price"])
    wl = ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[
            ToolDescriptor(name="search_mcp", description="", capabilities=[], configured=True),
        ],
        blocked_tools=[],
        reason_by_tool={},
    )
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.FINISH_STATE, arguments={})
    with pytest.raises(ValueError, match="not yet attempted"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state, wl)


def test_duku_opening_does_not_use_model_prior_as_required_evidence():
    contract = ResponseContractCompiler().compile(
        _frame(
            raw_query="独库公路每年几月份开放",
            entities=SemanticEntities(country="China", places=["独库公路"]),
            information_needs=["best_time_to_visit"],
        )
    )
    prior_ev = Evidence(
        source_name="knowledge_prior",
        source_type=SourceType.MODEL_PRIOR,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.GENERAL_SEASONAL_CONTEXT,
                value="一般夏季开放",
                confidence=0.5,
            )
        ],
    )
    report = EvidenceCoverageChecker().check(contract, [prior_ev], [])
    seasonal = next(i for i in report.items if i.claim_type == "seasonal_operation_status")
    assert seasonal.covered is False


def test_composer_distinguishes_missing_required_and_prior_context():
    contract = ResponseContractCompiler().compile(
        _frame(
            raw_query="独库公路每年几月份开放",
            entities=SemanticEntities(country="China", places=["独库公路"]),
            information_needs=["best_time_to_visit"],
        )
    )
    prior_ev = Evidence(
        source_name="knowledge_prior",
        source_type=SourceType.MODEL_PRIOR,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.GENERAL_SEASONAL_CONTEXT,
                value="一般6-10月通车",
                confidence=0.45,
            )
        ],
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="独库公路每年几月份开放")
    state.response_contract = contract
    state.coverage_report = EvidenceCoverageChecker().check(contract, [prior_ev], [])
    state.evidence = [prior_ev]
    bundle = AnswerComposerAgent()._build_input_bundle(state, {"compose_mode": "advisory"})
    rules = bundle["composition_rules"]
    assert any("Missing required claim seasonal_operation_status" in r for r in rules)
    assert any("model-prior" in r.lower() or "prior" in r.lower() for r in rules)


def test_region_on_poi_entity_flows_to_semantic_frame():
    from app.agents.normalized_request_to_semantic_frame import NormalizedRequestToSemanticFrame
    from app.schemas.normalized_user_request import NormalizedEntity, NormalizedUserRequest

    req = NormalizedUserRequest(
        raw_query="新疆的独库公路每年几月份开放？",
        rewritten_query="新疆独库公路开放月份",
        entities=[
            NormalizedEntity(
                text="独库公路",
                normalized_name="独库公路",
                entity_type="natural_site",
                country="China",
                region="新疆",
            )
        ],
    )
    frame = NormalizedRequestToSemanticFrame.convert(req)
    assert frame.entities.region == "新疆"
    assert frame.entities.places == ["独库公路"]


def test_hengshan_ambiguity_preserves_keywords_without_clarification():
    frame = _frame(
        raw_query="衡山景区票价如何？",
        normalized_request="衡山景区门票价格",
        decision_type=DecisionType.FACT_LOOKUP,
        task_family=TaskFamily.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["衡山"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
        place_ambiguity=PlaceAmbiguityInfo(
            is_ambiguous=True,
            reason="衡山可能指南岳衡山或北岳恒山",
            candidates=[
                PlaceAmbiguityCandidate(name="南岳衡山", region="湖南", city="衡阳"),
                PlaceAmbiguityCandidate(name="北岳恒山", region="山西", city="大同"),
            ],
        ),
        labeled_entities=[
            {
                "text": "衡山",
                "normalized_name": "衡山",
                "entity_type": "natural_site",
                "country": "China",
                "labels": ["primary_subject", "ambiguous_place_candidate"],
            }
        ],
    )
    contract = ResponseContractCompiler().compile(frame)
    assert contract.clarification_policy.should_ask is False
    assert contract.entity_policy.requires_disambiguation is False
    assert contract.place_ambiguity_context is not None
    assert contract.place_ambiguity_context.is_ambiguous is True
    keywords = contract.gated_search_keywords
    assert "衡山" in keywords
    assert "南岳衡山" in keywords
    assert "衡阳" in keywords
    assert "大同" in keywords
    assert "门票" in keywords


def test_baishahu_elevation_skips_s3_clarification_and_dispatches_evidence():
    frame = _frame(
        raw_query="白沙湖的海拔多少？",
        normalized_request="白沙湖海拔",
        decision_type=DecisionType.FACT_LOOKUP,
        task_family=TaskFamily.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["白沙湖"]),
        information_needs=["general_information"],
        requires_exact_fact=True,
        can_answer_with_model_prior=False,
    )
    contract = ResponseContractCompiler().compile(frame)
    assert contract.entity_policy.requires_disambiguation is False
    assert contract.clarification_policy.should_ask is False
    assert "白沙湖" in contract.gated_search_keywords
    assert "海拔" in contract.gated_search_keywords
    general = next(c for c in contract.claim_requirements if c.claim_type == "general_travel_advice")
    assert general.priority == "required"
    assert general.requires_exact_fact is True

    sm = TravelAgentStateMachine()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.response_contract = contract
    assert sm._dispatch_from_contract(state) == "evidence_pipeline"


def test_duku_with_xinjiang_skips_disambiguation_and_dispatches_evidence():
    frame = _frame(
        raw_query="新疆的独库公路每年几月份开放？",
        normalized_request="新疆独库公路开放月份",
        entities=SemanticEntities(country="China", region="新疆", places=["独库公路"]),
        information_needs=["best_time_to_visit"],
    )
    contract = ResponseContractCompiler().compile(frame)
    assert contract.entity_policy.requires_disambiguation is False
    assert contract.clarification_policy.should_ask is False
    assert any(c.claim_type == "seasonal_operation_status" for c in contract.claim_requirements)

    sm = TravelAgentStateMachine()
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.response_contract = contract
    assert sm._dispatch_from_contract(state) == "evidence_pipeline"


def test_state_machine_contract_forces_evidence_pipeline():
    contract = ResponseContractCompiler().compile(
        _frame(
            raw_query="独库公路每年几月份开放",
            entities=SemanticEntities(country="China", places=["独库公路"]),
            information_needs=["best_time_to_visit"],
        )
    )
    sm = TravelAgentStateMachine()
    assert sm._requires_full_evidence_pipeline(contract) is True
    assert sm._allows_prior_advisory(contract) is False

    advisory_contract = ResponseContractCompiler().compile(
        _frame(
            raw_query="云峰山什么时候去",
            entities=SemanticEntities(country="China", city="连云港", places=["云峰山"]),
            information_needs=["best_time_to_visit"],
        )
    )
    assert sm._requires_full_evidence_pipeline(advisory_contract) is False
    assert sm._allows_prior_advisory(advisory_contract) is True

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="独库公路")
    state.response_contract = contract
    assert sm._dispatch_from_contract(state) == "evidence_pipeline"
