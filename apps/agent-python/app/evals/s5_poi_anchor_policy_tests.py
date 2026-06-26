"""S5 mandatory POI anchor policy tests (nearby task classes only)."""

from __future__ import annotations

import pytest

from app.agents.s5_evidence_orchestrator_agent import S5EvidenceOrchestratorAgent
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_poi_anchor_policy import (
    blocks_subagent_until_poi_anchor,
    mandatory_poi_entity_required,
    poi_anchor_satisfied,
    task_requires_mandatory_poi_anchor,
)
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.semantic_frame import (
    DecisionType,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_query import TravelAgentState


def _nearby_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="戏马台附近有什么好吃的？",
        normalized_request="戏马台附近美食",
        information_needs=["nearby_food"],
        decision_type=DecisionType.NEARBY_SEARCH,
        task_family=TaskFamily.FOOD,
        entities=SemanticEntities(country="China", city="徐州", places=["戏马台"], region="江苏"),
        time_scope=TimeScope.FLEXIBLE,
        can_answer_with_model_prior=False,
    )
    profile = IntentProfileDeriver().derive(frame)
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
        intent_profile=profile,
        response_contract=contract,
        travel_task=TravelTask(task_type=TravelTaskType.FOOD_NEARBY, country="China", city="徐州"),
    )


def _lookup_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="衡山景区门票多少钱？",
        normalized_request="衡山门票",
        information_needs=["ticket_price"],
        decision_type=DecisionType.FACT_LOOKUP,
        task_family=TaskFamily.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["衡山"]),
        requires_exact_fact=True,
    )
    profile = IntentProfileDeriver().derive(frame)
    return TravelAgentState(
        session_id="s",
        query_id="q2",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
        intent_profile=profile,
    )


def test_nearby_task_class_requires_mandatory_poi():
    state = _nearby_state()
    assert task_requires_mandatory_poi_anchor(state)
    assert mandatory_poi_entity_required(state)
    assert not poi_anchor_satisfied(state)


def test_lookup_task_class_does_not_require_mandatory_poi():
    state = _lookup_state()
    assert not task_requires_mandatory_poi_anchor(state)
    assert not mandatory_poi_entity_required(state)


def test_blocks_fact_search_until_entity_for_nearby_only():
    nearby = _nearby_state()
    lookup = _lookup_state()
    assert blocks_subagent_until_poi_anchor(nearby, "fact_search_agent")
    assert not blocks_subagent_until_poi_anchor(nearby, "entity_resolution_agent")
    assert not blocks_subagent_until_poi_anchor(lookup, "fact_search_agent")


@pytest.mark.asyncio
async def test_orchestrator_returns_entity_before_llm_for_nearby():
    orch = S5EvidenceOrchestratorAgent(llm_client=None)
    state = _nearby_state()
    action = await orch.next_action(state, {"tool_whitelist": None}, step=0)
    assert action.action_type == AgentActionType.CALL_SUBAGENT
    assert action.target == "entity_resolution_agent"
    assert "戏马台" in (action.arguments.get("search_query") or "")


def test_policy_guard_rejects_fact_search_before_poi_anchor():
    state = _nearby_state()
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="fact_search_agent",
        arguments={
            "search_query": "徐州戏马台美食",
            "information_need": "nearby_food",
            "claim_target": "nearby_food",
        },
    )
    with pytest.raises(ValueError, match="entity_resolution_agent anchors POI"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_policy_guard_allows_fact_search_for_lookup_without_poi_gate():
    state = _lookup_state()
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="fact_search_agent",
        arguments={
            "search_query": "衡山门票",
            "information_need": "ticket_price",
            "claim_target": "ticket_price",
            "anchor_keywords": ["衡山"],
        },
    )
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)
