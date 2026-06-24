"""Tests for S5 evidence contradiction decomposer sub-agent."""

from __future__ import annotations

import json

import pytest

from app.agents.evidence_contradiction_decomposer_agent import EvidenceContradictionDecomposerAgent
from app.evals.llm_test_helpers import StubLLMClient
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.claim_adoption_policy import ClaimAdoptionPolicy
from app.orchestrator.claim_policy_registry import resolve_policy
from app.orchestrator.evidence_signal_utils import multi_value_signal_for_need, ticket_price_amounts
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _kanas_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="喀纳斯景区的票价多少？",
        normalized_request="喀纳斯景区的票价多少？",
        task_family=TaskFamily.FACT_LOOKUP,
        entities=SemanticEntities(country="China", region="新疆", city="Altay", places=["喀纳斯景区"]),
        information_needs=["ticket_price"],
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.response_contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(
                claim_type="ticket_price",
                claim_family="ticket_booking",
                claim_description="门票价格",
                priority="required",
            )
        ]
    )
    state.structured_result = {
        "completed_search_task_ids": ["a", "b"],
        "search_tasks": [],
    }
    state.evidence = [
        Evidence(
            evidence_id="e1",
            source_name="open-webSearch",
            source_type=SourceType.WEB,
            country="China",
            place_name="喀纳斯景区",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE,
                    value="喀纳斯景区门票及区间车车票价格_喀纳斯景区管理委员会: 喀纳斯景区门票价格旺季160元/人2天、淡季80元/人2天",
                    confidence=0.55,
                )
            ],
        ),
        Evidence(
            evidence_id="e2",
            source_name="open-webSearch",
            source_type=SourceType.WEB,
            country="China",
            place_name="喀纳斯景区",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE,
                    value="一进票:230元(门160元+车70元)",
                    confidence=0.55,
                )
            ],
        ),
        Evidence(
            evidence_id="e3",
            source_name="open-webSearch",
            source_type=SourceType.WEB,
            country="China",
            place_name="喀纳斯景区",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE,
                    value="门票70元/人，区间车75元/人",
                    confidence=0.55,
                )
            ],
        ),
    ]
    return state


def test_ticket_price_amounts_detect_multiple_values():
    state = _kanas_state()
    amounts = ticket_price_amounts(state.evidence)
    assert amounts >= {70, 80, 160, 230}
    assert multi_value_signal_for_need(state, "ticket_price")


@pytest.mark.asyncio
async def test_heuristic_decomposer_splits_ticket_tiers():
    agent = EvidenceContradictionDecomposerAgent(llm_client=StubLLMClient(lambda _s, _u: "{}"))
    out = await agent.run(_kanas_state())
    assert out["decomposed"] is True
    block = out["decompositions"][0]
    assert block["claim_type"] == "ticket_price"
    labels = " ".join(item["label"] for item in block["items"])
    assert "160" in labels or any("160" in item["value"] for item in block["items"])
    assert "230" in labels or any("230" in item["value"] for item in block["items"])


@pytest.mark.asyncio
async def test_llm_decomposer_parses_structured_output():
    payload = {
        "decompositions": [
            {
                "claim_type": "ticket_price",
                "summary": "差异来自票种口径",
                "items": [
                    {
                        "label": "景区门票",
                        "value": "旺季160元",
                        "confidence": 0.8,
                        "evidence_ids": [],
                        "supporting_snippets": [],
                    }
                ],
                "outliers": [],
            }
        ],
        "presentation_guidance": "分列呈现",
        "follow_up_search_tasks": [],
    }
    agent = EvidenceContradictionDecomposerAgent(
        llm_client=StubLLMClient(lambda _s, _u: json.dumps(payload, ensure_ascii=False))
    )
    out = await agent.run(_kanas_state())
    assert out["decomposed"] is True
    assert out["decompositions"][0]["items"][0]["value"] == "旺季160元"


def test_controller_routes_contradiction_decomposer_when_due():
    state = _kanas_state()
    controller = ActionModelController(llm_client=None)
    ctx: dict = {}
    assert controller._contradiction_decompose_due(state, ctx) is True
    action = controller._contradiction_decompose_action(state, ctx)
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "evidence_contradiction_decomposer_agent"


def test_evidence_guard_accepts_decomposer_subagent():
    state = _kanas_state()
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="evidence_contradiction_decomposer_agent",
        arguments={},
    )
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_ticket_price_adoption_with_decomposition_not_refuse():
    policy = resolve_policy(
        ClaimRequirement(
            claim_type="ticket_price",
            claim_family="ticket_booking",
            claim_description="门票",
            priority="required",
        )
    )
    adoption = ClaimAdoptionPolicy()
    decomp = [
        {
            "claim_type": "ticket_price",
            "items": [
                {"label": "仅门票", "value": "旺季160元", "confidence": 0.75},
                {"label": "门+车", "value": "230元", "confidence": 0.7},
            ],
        }
    ]
    decision, _ = adoption.decide(policy, [], [], preferred_id=None, evidence=[], fact_decomposition=decomp)
    assert decision.adoption == "adopt_with_limitation"
    assert decision.coverage_quality == "partial"
