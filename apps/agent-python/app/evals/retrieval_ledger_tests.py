"""Phase 1 — RetrievalAttemptLedger, claim whitelist, limitations."""

from __future__ import annotations

import pytest

from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claim_gap_fill_planner import order_gap_tools
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft
from app.orchestrator.retrieval_attempt_ledger import (
    get_ledger,
    record_skip,
    retrieval_complete,
    save_ledger,
)
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.ticket_lookup_policy import filter_user_visible_limitations
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.evals.ticket_test_helpers import mark_opening_hours_families_attempted, mark_ticket_families_attempted


def _opening_hours_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="故宫博物院开放时间？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="北京", places=["故宫博物院"]),
        information_needs=["opening_hours"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=["opening_hours"],
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def _kanas_boat_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="喀纳斯湖游船船票多少钱？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="阿勒泰", places=["喀纳斯湖"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=["ticket_price"],
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q2", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def test_s5_finish_opening_hours_without_claim_coverage():
    state = _opening_hours_state()
    mark_opening_hours_families_attempted(state)
    assert retrieval_complete(state, "opening_hours")
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.FINISH_STATE, arguments={})
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_official_discovery_skip_counts_as_family_attempted():
    state = _opening_hours_state()
    record_skip(state, "official_source", "no_urls_or_search_results", claim_type="opening_hours")
    ledger = get_ledger(state, "opening_hours")
    assert "official_source" in ledger.families_attempted()


def test_opening_hours_whitelist_excludes_ticket_platform_tools(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    state = _opening_hours_state()
    wl = ToolWhitelistBuilder().build(state)
    allowed = set(wl.allowed_tool_names())
    assert "fliggy_ticket_api_mcp" not in allowed
    assert "dianping_ticket_signal_crawler_mcp" not in allowed
    assert "search_mcp" in allowed


def test_ticket_price_whitelist_includes_platform_tools(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    state = _kanas_boat_state()
    wl = ToolWhitelistBuilder().build(state)
    allowed = set(wl.allowed_tool_names())
    assert "fliggy_ticket_api_mcp" in allowed or "dianping_ticket_signal_crawler_mcp" in allowed


def test_gap_fill_opening_hours_search_before_discovery():
    state = _opening_hours_state()
    tools = [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "search_mcp",
        "browser_mcp",
    ]
    ordered = order_gap_tools(state, tools, claim_type="opening_hours")
    assert ordered[0] == "search_mcp"
    assert ordered.index("search_mcp") < ordered.index("official_source_discovery_mcp")


def test_max_steps_not_in_user_visible_limitations():
    state = _kanas_boat_state()
    state.internal_debug_limitations = ["evidence_planning_and_tool_use reached max_steps"]
    state.user_visible_limitations = ["未能读取官方页面确认票价。"]
    draft = build_fact_lookup_draft(state)
    text = " ".join(draft.limitations or [])
    assert "max_steps" not in text
    assert "未能读取" in text or not draft.limitations


def test_filter_user_visible_strips_internal_debug():
    raw = [
        "Cannot FINISH evidence planning",
        "evidence_planning_and_tool_use reached max_steps",
        "平台票价可能随日期变化。",
    ]
    kept = filter_user_visible_limitations(raw)
    assert "Cannot FINISH" not in " ".join(kept)
    assert any("平台票价" in x for x in kept)


def test_ticket_retrieval_complete_via_ledger(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    state = _kanas_boat_state()
    mark_ticket_families_attempted(state)
    assert retrieval_complete(state, "ticket_price")
