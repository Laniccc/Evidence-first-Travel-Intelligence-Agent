"""Unit tests for LookupResearchChain schema and orchestration helpers."""

from __future__ import annotations

from app.orchestrator.lookup_query_objectives import (
    build_lookup_query_objectives,
    objective_to_search_query,
)
from app.orchestrator.lookup_research_chain import (
    build_lookup_research_context,
    ensure_lookup_chain_initialized,
    get_lookup_chain,
    is_duplicate_lookup_attempt,
    lookup_attempt_signature,
    lookup_phase_order,
    lookup_mandatory_entity_anchor,
    mark_phase_complete,
    next_recommended_phase,
    record_lookup_attempt,
)
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _terracotta_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="兵马俑门票多少钱？",
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="西安", places=["兵马俑"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=[],
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_strategy = resolve_intent_strategy(profile)
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def test_lookup_phase_order_ticket_price():
    phases = lookup_phase_order("ticket_price")
    assert phases[0] == "research_frame"
    assert "official_site_discovery" in phases
    assert "platform_ticket_candidate" in phases
    assert phases[-1] == "retrieval_audit"


def test_initialize_lookup_chain_writes_structured_result():
    state = _terracotta_state()
    chain = ensure_lookup_chain_initialized(state)
    assert chain.frame is not None
    assert chain.frame.primary_fact_need == "ticket_price"
    assert "research_frame" in chain.completed_phases
    stored = (state.structured_result or {}).get("lookup_research_chain")
    assert stored is not None


def test_query_objectives_no_hardcoded_peak_names():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="黄山海拔多少米？",
    )
    state.semantic_frame = SemanticFrame(
        raw_query="黄山海拔多少米？",
        task_family=TaskFamily.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["黄山"]),
        information_needs=["elevation"],
        requires_exact_fact=True,
    )
    ensure_lookup_chain_initialized(state)
    objs = build_lookup_query_objectives(state, "elevation", "geo_authority")
    assert objs
    query = objective_to_search_query(objs[0])
    assert "黄山" in query
    assert "莲花峰" not in query
    assert "海拔" in query


def test_lookup_attempt_dedup():
    state = _terracotta_state()
    sig = lookup_attempt_signature(
        subagent="fact_lookup_agent",
        claim_type="ticket_price",
        phase="official_discovery",
        source_family="official_operator",
        objective="official_ticket_price",
    )
    assert not is_duplicate_lookup_attempt(state, sig)
    record_lookup_attempt(state, sig)
    assert is_duplicate_lookup_attempt(state, sig)


def test_phase_progression_after_entity_anchor():
    state = _terracotta_state()
    ensure_lookup_chain_initialized(state)
    assert next_recommended_phase(state) == "entity_anchor" or lookup_mandatory_entity_anchor(state, 0) is False
    state.structured_result = {
        **(state.structured_result or {}),
        "fact_anchor": {"resolved_name": "秦始皇帝陵博物院", "city": "西安"},
    }
    mark_phase_complete(state, "entity_anchor")
    nxt = next_recommended_phase(state)
    assert nxt in {
        "official_site_discovery",
        "official_ticket_page_discovery",
        "platform_ticket_candidate",
        "official_discovery",
        "fact_acquisition",
        "retrieval_audit",
        None,
    }


def test_build_lookup_research_context_keys():
    state = _terracotta_state()
    ctx = build_lookup_research_context(state)
    assert ctx["lookup_phase_order"]
    assert "forbidden_shortcuts" in ctx
    assert ctx["next_recommended_phase"]


def test_fact_s5_planning_context_includes_chain():
    from app.orchestrator.fact_lookup_task_orchestration import fact_s5_planning_context

    state = _terracotta_state()
    ctx = fact_s5_planning_context(state)
    assert ctx["lookup_research_chain"]
    assert ctx["s5_task_class"] == "ticket_price_lookup"


def test_fact_lookup_agent_defaults_to_ticket_phase():
    from app.agents.fact_lookup_agent import _default_phase_and_family
    from app.orchestrator.lookup_research_chain import ensure_lookup_chain_initialized

    state = _terracotta_state()
    ensure_lookup_chain_initialized(state)
    phase, family = _default_phase_and_family(
        state,
        requested_phase=None,
        requested_family=None,
        claim_target="ticket_price",
    )
    assert phase in {"official_site_discovery", "official_ticket_page_discovery"}
    assert family in {"official_operator", "government_tourism"}
