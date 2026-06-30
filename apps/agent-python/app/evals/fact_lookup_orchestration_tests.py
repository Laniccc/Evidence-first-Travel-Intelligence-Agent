"""Tests for strict_fact_lookup task orchestration and guided composition."""

from __future__ import annotations

from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft
from app.orchestrator.fact_lookup_policy import (
    collect_fact_clues,
    is_fact_lookup_task,
    pipeline_search_queries,
    pipeline_search_query,
    primary_fact_need_from_state,
)
from app.orchestrator.fact_lookup_anchor_policy import select_fact_anchor_candidate
from app.orchestrator.fact_lookup_task_orchestration import (
    fact_s5_may_finish_early,
    fact_s5_skip_fact_search,
    resolve_fact_lookup_compose_mode,
    should_use_fact_lookup_guided_compose,
)
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
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


def test_terracotta_is_fact_lookup_task():
    state = _terracotta_state()
    assert is_fact_lookup_task(state)
    assert primary_fact_need_from_state(state) == "ticket_price"


def test_pipeline_search_query_official_wording():
    state = _terracotta_state()
    q = pipeline_search_query(state, "ticket_price")
    assert "兵马俑" in q
    assert "门票" in q


def _huangshan_elevation_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="黄山海拔多少米？",
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["黄山"]),
        information_needs=["elevation"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=["elevation"],
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


def test_elevation_pipeline_uses_objective_queries():
    state = _huangshan_elevation_state()
    queries = pipeline_search_queries(state, "elevation")
    assert any("海拔" in q for q in queries)
    assert not any("莲花峰" in q for q in queries)
    assert not any("主峰" in q for q in queries)


def test_elevation_anchor_prefers_scenic_over_city():
    candidates = [
        {"name": "黄山市", "city": "黄山市", "province": "安徽省"},
        {"name": "黄山风景区", "city": "黄山市", "province": "安徽省", "tag": "风景名胜"},
    ]
    chosen = select_fact_anchor_candidate(candidates, raw_place="黄山", need="elevation")
    assert chosen is not None
    assert "风景区" in chosen["name"]


def test_fact_s5_finish_after_lookup_without_claims_waits_for_gap_fill():
    state = _huangshan_elevation_state()
    state.structured_result = {"subagent_results": [{"subagent": "fact_lookup_agent", "evidence_count": 0}]}
    assert not fact_s5_may_finish_early(state, step=1)
    assert not fact_s5_skip_fact_search(state)


def test_fact_lookup_guided_draft_with_ticket_evidence():
    state = _terracotta_state()
    state.evidence = [
        Evidence(
            evidence_id="ev1",
            source_name="陕西省文化和旅游厅",
            source_type=SourceType.OFFICIAL,
            source_url="https://www.shaanxi.gov.cn/",
            country="China",
            city="西安",
            place_name="秦始皇兵马俑博物馆",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE,
                    value="成人票 120 元",
                    confidence=0.75,
                )
            ],
            confidence=0.75,
        )
    ]
    clues = collect_fact_clues(state)
    assert len(clues) == 1
    assert clues[0]["official"] is True
    draft = build_fact_lookup_draft(state)
    text = draft.render_text()
    assert "120" in text
    assert "无法确认" not in text


def test_fact_lookup_guided_draft_prioritizes_platform_ticket_candidate():
    state = _terracotta_state()
    state.evidence = [
        Evidence(
            evidence_id="ev-fliggy",
            source_name="Fliggy Open API",
            source_type=SourceType.TICKET_PLATFORM,
            source_url="https://a.feizhu.com/1HPCRe",
            country="China",
            city="南京",
            place_name="栖霞山",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value="¥48",
                    confidence=0.62,
                ),
                Claim(
                    claim_type=ClaimType.TICKET_TYPE,
                    value="大门票（当日可订） 成人票",
                    confidence=0.55,
                ),
                Claim(
                    claim_type=ClaimType.PLATFORM_TICKET_URL,
                    value="https://a.feizhu.com/1HPCRe",
                    confidence=0.55,
                ),
            ],
            confidence=0.62,
        )
    ]

    draft = build_fact_lookup_draft(state)
    text = draft.render_text()

    assert "48" in text
    assert "大门票" in text
    assert "平台候选价" in text
    assert "官方页面价格" in text


def test_fact_lookup_guided_draft_without_evidence():
    state = _terracotta_state()
    draft = build_fact_lookup_draft(state)
    text = draft.render_text()
    assert "无法确认" in text


def test_fact_s5_finish_and_skip_after_lookup_with_audit_finish():
    state = _terracotta_state()
    state.evidence = [
        Evidence(
            evidence_id="ev1",
            source_name="Web",
            source_type=SourceType.WEB,
            country="China",
            claims=[Claim(claim_type=ClaimType.TICKET_PRICE, value="120元", confidence=0.55)],
            confidence=0.55,
        )
    ]
    state.structured_result = {
        "subagent_results": [{"subagent": "fact_lookup_agent", "evidence_count": 3}],
        "lookup_research_chain": {
            "current_phase": "retrieval_audit",
            "completed_phases": ["research_frame", "source_plan", "official_discovery"],
            "audit": {"recommended_next": "finish", "official_fact_found": False},
        },
    }
    assert fact_s5_may_finish_early(state, step=2)
    assert fact_s5_skip_fact_search(state)


def test_resolve_fact_lookup_compose_mode():
    state = _terracotta_state()
    state.structured_result = {"subagent_results": [{"subagent": "fact_lookup_agent"}]}
    state.evidence = [
        Evidence(
            evidence_id="ev1",
            source_name="Web",
            source_type=SourceType.WEB,
            country="China",
            claims=[Claim(claim_type=ClaimType.PRICE_CANDIDATE, value="120元", confidence=0.5)],
            confidence=0.5,
        )
    ]
    assert should_use_fact_lookup_guided_compose(state)
    assert resolve_fact_lookup_compose_mode(state) == "fact_lookup_guided"


def test_state_reducer_merges_fact_lookup_agent_output():
    from app.orchestrator.actions import ActionResult, AgentAction, AgentActionType
    from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
    from app.orchestrator.state_reducer import StateReducer

    state = _terracotta_state()
    evidence = Evidence(
        evidence_id="ev-fact",
        source_name="Official",
        source_type=SourceType.WEB,
        country="China",
        place_name="兵马俑",
        claims=[Claim(claim_type=ClaimType.TICKET_PRICE, value="120元", confidence=0.7)],
        confidence=0.7,
    )
    action = AgentAction(
        action_type=AgentActionType.CALL_SUBAGENT,
        target="fact_lookup_agent",
        arguments={"task_id": "fact-test"},
    )
    result = ActionResult(
        ok=True,
        output={
            "subagent": "fact_lookup_agent",
            "task_id": "fact-test",
            "search_query": "兵马俑",
            "evidence": [evidence],
            "tool_traces": [],
        },
    )
    updated = StateReducer().apply(state, action, result, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY)
    assert len(updated.evidence) == 1
    sub_results = (updated.structured_result or {}).get("subagent_results") or []
    assert any(r.get("subagent") == "fact_lookup_agent" for r in sub_results)


def test_action_executor_registers_fact_lookup_agent():
    import inspect

    from app.orchestrator.action_executor import ActionExecutor

    source = inspect.getsource(ActionExecutor._call_subagent)
    assert 'name == "fact_lookup_agent"' in source


def test_response_contract_lookup_claim_family():
    state = _terracotta_state()
    claim = state.response_contract.claim_requirements[0]
    assert claim.claim_family == "ticket_booking"
    assert claim.model_prior_allowed is False


def test_evidence_gap_request_query_objectives():
    from app.orchestrator.evidence_gap_planner import EvidenceGapPlanner
    from app.orchestrator.claim_policy_registry import resolve_policy
    from app.schemas.evidence_decision_report import ClaimDecision

    state = _terracotta_state()
    claim = state.response_contract.claim_requirements[0]
    policy = resolve_policy(claim)
    decision = ClaimDecision(
        claim_type=claim.claim_type,
        adoption="omit",
        coverage_quality="none",
        reason="missing official",
    )
    gap = EvidenceGapPlanner().plan_gaps(state, claim, policy, decision, gap_round=0, max_gap_rounds=2)
    assert gap is not None
    assert gap.query_objectives
    assert gap.query_objective


def test_fact_lookup_agent_accepts_string_query_objectives():
    from app.agents.fact_lookup_agent import _normalize_query_objectives, _objective_key

    objs = _normalize_query_objectives(["geo_elevation"])
    assert objs == [{"objective": "geo_elevation"}]
    assert _objective_key(objs, "geo_authority") == "geo_elevation"


def test_debug_log_surfaces_unknown_subagent():
    from app.debug_session_log import _limitations_diagnostics

    diag = _limitations_diagnostics(
        ["Unknown subagent: fact_lookup_agent"] * 5 + ["other limitation"]
    )
    assert diag["unknown_subagents"]["fact_lookup_agent"] == 5
    assert diag["other"] == ["other limitation"]

