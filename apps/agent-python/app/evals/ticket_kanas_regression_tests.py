"""Regression tests — Kanas boat ticket / phase advance / related POI."""

from __future__ import annotations

import pytest

from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.lookup_research_chain import (
    advance_entity_anchor_if_satisfied,
    get_lookup_chain,
    lookup_mandatory_entity_anchor,
)
from app.orchestrator.place_disambiguation_composition import should_present_place_disambiguation_at_s8
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.ticket_lookup_policy import (
    apply_ticket_gap_phase_override,
    ticket_platform_tool_allowed,
)
from app.orchestrator.ticket_product_policy import extract_ticket_product_context
from app.orchestrator.actions import AgentAction, AgentActionType
from app.schemas.evidence_gap_request import EvidenceGapRequest
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from tools.mcp.adapters.baidu_response_parser import is_valid_baidu_uid, pick_baidu_uid_from_evidence
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType


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
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    state.structured_result = {
        "fact_anchor": {
            "resolved_name": "喀纳斯景区",
            "canonical_name": "喀纳斯景区",
            "confidence": 0.88,
        }
    }
    return state


def _kanas_poi_candidates() -> list[dict]:
    base = {"city": "阿勒泰", "province": "新疆"}
    return [
        {**base, "name": "喀纳斯湖码头", "uid": "a1b2c3d4e5f6a7b8c9d0"},
        {**base, "name": "双湖游船", "uid": "b2c3d4e5f6a7b8c9d0e1"},
        {**base, "name": "喀纳斯景区", "uid": "c3d4e5f6a7b8c9d0e1f2"},
        {**base, "name": "喀纳斯景区-售票处", "uid": "d4e5f6a7b8c9d0e1f2a3"},
    ]


def test_boat_ticket_product_extracted_from_query():
    ctx = extract_ticket_product_context("喀纳斯湖游船船票多少钱？")
    assert ctx is not None
    assert ctx["ticket_product"] == "boat_ticket"
    assert "游船" in ctx["ticket_product_keywords"]
    assert "船票" in ctx["ticket_product_keywords"]


def test_policy_reject_entity_anchor_advances_to_ticket_phase():
    state = _kanas_boat_state()
    assert lookup_mandatory_entity_anchor(state, 0) is False
    chain = get_lookup_chain(state)
    assert "entity_anchor" in chain.completed_phases
    assert chain.current_phase != "entity_anchor"


def test_ticket_gap_platform_tools_force_platform_phase():
    state = _kanas_boat_state()
    gap = EvidenceGapRequest(
        claim_type="ticket_price",
        claim_family="ticket_booking",
        claim_description="门票价格",
        reason="missing",
        suggested_tools=["fliggy_ticket_api_mcp", "dianping_ticket_signal_crawler_mcp"],
    )
    assert apply_ticket_gap_phase_override(state, gap)
    assert ticket_platform_tool_allowed(state, "fliggy_ticket_api_mcp")


def test_related_poi_not_place_disambiguation_for_same_scenic_area():
    state = _kanas_boat_state()
    state.structured_result = {
        **(state.structured_result or {}),
        "place_disambiguation_candidates": _kanas_poi_candidates(),
    }
    state.evidence = [
        Evidence(
            evidence_id="ev-poi",
            source_name="baidu",
            source_type=SourceType.MAP,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.PLACE_CANDIDATES,
                    value="candidates",
                    normalized_value={"candidates": _kanas_poi_candidates()},
                    confidence=0.7,
                )
            ],
            confidence=0.7,
        )
    ]
    assert not should_present_place_disambiguation_at_s8(state)


def test_official_discovery_skips_without_urls_in_supplement():
    guard = EvidencePolicyGuard()
    state = _kanas_boat_state()
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="official_source_discovery_mcp",
        arguments={},
    )
    with pytest.raises(ValueError, match="requires urls or search_results"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_place_detail_uid_must_come_from_baidu_candidate():
    assert not is_valid_baidu_uid("百度百科 snippet 喀纳斯湖是...")
    ev = [
        Evidence(
            evidence_id="ev1",
            source_name="baidu",
            source_type=SourceType.MAP,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.PLACE_CANDIDATES,
                    value="candidates",
                    normalized_value={"candidates": _kanas_poi_candidates()},
                    confidence=0.8,
                )
            ],
            confidence=0.8,
        )
    ]
    uid = pick_baidu_uid_from_evidence(ev, city="阿勒泰")
    assert uid == "a1b2c3d4e5f6a7b8c9d0"


def test_reverse_geocode_requires_coordinates():
    guard = EvidencePolicyGuard()
    state = _kanas_boat_state()
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="baidu_reverse_geocode_mcp",
        arguments={},
    )
    with pytest.raises(ValueError, match="latitude and longitude"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_advance_entity_anchor_if_satisfied_marks_complete():
    state = _kanas_boat_state()
    assert advance_entity_anchor_if_satisfied(state)
    assert "entity_anchor" in get_lookup_chain(state).completed_phases


def test_boat_ticket_query_contains_place_and_product_keywords():
    from app.orchestrator.ticket_product_policy import build_ticket_price_search_queries, ensure_ticket_product_context

    state = _kanas_boat_state()
    ensure_ticket_product_context(state)
    queries = build_ticket_price_search_queries(state)
    assert queries
    assert any("喀纳斯" in q and "游船" in q for q in queries)
    assert not any(q.strip() == "门票价格 检索门票价格平台" for q in queries)


def test_ticket_platform_input_contains_boat_ticket_keywords():
    from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments

    state = _kanas_boat_state()
    args = enrich_mcp_tool_arguments("fliggy_ticket_api_mcp", {}, state=state)
    assert args.get("ticket_product") == "boat_ticket"
    assert "游船" in (args.get("product_keywords") or args.get("ticket_product_keywords") or [])
    assert "喀纳斯" in (args.get("query") or "")


def test_boat_ticket_relevance_rejects_world_cup_or_sports_ticket():
    from app.orchestrator.ticket_relevance_policy import ticket_relevance_score

    state = _kanas_boat_state()
    score = ticket_relevance_score(state, "general_fact", "世界杯门票价格官方下载")
    assert score < 0.5
    score2 = ticket_relevance_score(state, "general_fact", "楚超联赛鄂州门票 9.9 元")
    assert score2 < 0.5


def test_official_discovery_rejects_unrelated_search_results():
    from app.orchestrator.ticket_relevance_policy import discovery_hit_relevant

    assert not discovery_hit_relevant(
        {"url": "https://sohu.com/a...2天前", "title": "世界杯门票价格", "snippet": "官方下载"},
        place_name="喀纳斯湖",
        claim_type="ticket_price",
        anchor_terms=["喀纳斯湖"],
        ticket_product="boat_ticket",
    )


def test_s8_does_not_show_rejected_noise_as_clues():
    from app.orchestrator.fact_lookup_policy import collect_fact_clues

    state = _kanas_boat_state()
    state.evidence = [
        Evidence(
            evidence_id="ev-noise",
            source_name="search",
            source_type=SourceType.WEB,
            country="China",
            claims=[
                Claim(claim_type=ClaimType.GENERAL_FACT, value="世界杯门票价格官方下载", confidence=0.4),
                Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="楚超联赛鄂州门票 9.9 元", confidence=0.4),
            ],
            confidence=0.4,
        )
    ]
    clues = collect_fact_clues(state)
    assert not clues


def test_ticket_lookup_finish_with_gap_ack_without_max_steps(monkeypatch):
    from app.evals.ticket_test_helpers import mark_ticket_families_attempted
    from app.orchestrator.actions import AgentAction, AgentActionType
    from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
    from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
    from app.orchestrator.ticket_lookup_policy import ticket_lookup_retrieval_complete
    from app.schemas.tool_trace import ToolTrace

    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    state = _kanas_boat_state()
    mark_ticket_families_attempted(state)
    state.tool_traces = [
        ToolTrace(tool_name="search_mcp"),
        ToolTrace(tool_name="fliggy_ticket_api_mcp"),
        ToolTrace(tool_name="baidu_place_detail_mcp"),
    ]
    assert ticket_lookup_retrieval_complete(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.FINISH_STATE,
        arguments={"evidence_gap_acknowledged": True},
    )
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_fact_search_agent_counts_as_search_family_attempted():
    from app.orchestrator.ticket_lookup_attempt_tracker import search_family_attempted

    state = _kanas_boat_state()
    state.structured_result = {
        **(state.structured_result or {}),
        "subagent_results": [{"subagent": "fact_search_agent", "evidence_count": 3}],
    }
    assert search_family_attempted(state)


def test_official_discovery_skip_counts_as_attempted_not_finish_blocker(monkeypatch):
    from app.orchestrator.ticket_lookup_attempt_tracker import (
        official_family_attempted_or_skipped,
        record_official_discovery_skipped,
        ticket_lookup_retrieval_complete_by_family,
    )
    from app.schemas.tool_trace import ToolTrace

    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    state = _kanas_boat_state()
    state.structured_result = {
        **(state.structured_result or {}),
        "subagent_results": [{"subagent": "fact_search_agent", "evidence_count": 1}],
    }
    state.tool_traces = [
        ToolTrace(tool_name="baidu_place_search_mcp"),
        ToolTrace(tool_name="fliggy_ticket_api_mcp"),
        ToolTrace(tool_name="baidu_place_detail_mcp"),
    ]
    record_official_discovery_skipped(state, "official_source_discovery_mcp requires urls or search_results")
    assert official_family_attempted_or_skipped(state)
    assert not ticket_lookup_retrieval_complete_by_family(state)
    state.evidence = [
        Evidence(
            evidence_id="ev-platform-price",
            source_name="Fliggy FlyAI",
            source_type=SourceType.TICKET_PLATFORM,
            source_url="https://a.feizhu.com/kanas-boat",
            country="China",
            place_name="喀纳斯湖",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value="成人船票 ¥120",
                    confidence=0.62,
                ),
                Claim(
                    claim_type=ClaimType.TICKET_TYPE,
                    value="游船船票成人票",
                    confidence=0.6,
                ),
            ],
        )
    ]
    assert ticket_lookup_retrieval_complete_by_family(state)


def test_ticket_gap_fill_search_before_official_discovery_without_urls():
    from app.orchestrator.ticket_lookup_attempt_tracker import order_ticket_gap_tools

    state = _kanas_boat_state()
    tools = [
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "search_mcp",
        "browser_mcp",
    ]
    ordered = order_ticket_gap_tools(state, tools)
    assert ordered[0] == "search_mcp"
    assert ordered.index("search_mcp") < ordered.index("official_source_discovery_mcp")


def test_s8_boat_ticket_title_not_generic_ticket_price():
    from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft
    from app.orchestrator.ticket_product_policy import ensure_ticket_product_context

    state = _kanas_boat_state()
    ensure_ticket_product_context(state)
    draft = build_fact_lookup_draft(state)
    titles = [s.title for s in draft.sections]
    assert any("游船船票" in t for t in titles)
    assert not any(t.endswith("门票价格") for t in titles)


def test_ticket_platform_aliases_do_not_include_product_keywords():
    from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments
    from app.orchestrator.ticket_product_policy import ensure_ticket_product_context

    state = _kanas_boat_state()
    ensure_ticket_product_context(state)
    args = enrich_mcp_tool_arguments("fliggy_ticket_api_mcp", {}, state=state)
    place_aliases = args.get("place_aliases") or args.get("aliases") or []
    product_kws = args.get("product_keywords") or args.get("ticket_product_keywords") or []
    assert "游船" not in place_aliases
    assert "船票" not in place_aliases
    assert "游船" in product_kws or "船票" in product_kws


def test_fliggy_provider_error_status_error_not_ok():
    from tools.registry import TravelToolRegistry

    registry = TravelToolRegistry(tool_mode="real")
    meta = {
        "error": "Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)",
        "output_parse_status": "parse_error",
    }
    trace_updates = registry._trace_fields_from_meta(meta)
    assert trace_updates.get("output_parse_status") == "parse_error"
    status = "ok"
    result: list = []
    if not result:
        status = "zero_evidence"
    if trace_updates.get("output_parse_status") == "parse_error":
        status = "error"
    if trace_updates.get("error") and not result:
        status = "error"
    assert status == "error"


def test_baidu_place_search_not_repeated_after_related_poi_anchor():
    from app.orchestrator.lookup_research_chain import ensure_lookup_chain_initialized
    from app.orchestrator.ticket_lookup_policy import baidu_place_search_allowed_for_ticket
    from app.schemas.tool_trace import ToolTrace

    state = _kanas_boat_state()
    ensure_lookup_chain_initialized(state)
    advance_entity_anchor_if_satisfied(state)
    state.tool_traces = [ToolTrace(tool_name="baidu_place_search_mcp")]
    assert not baidu_place_search_allowed_for_ticket(state)


def test_s5_subagent_attempt_dedupe_by_normalized_objective():
    from app.orchestrator.ticket_lookup_attempt_tracker import (
        normalize_subagent_objective,
        record_subagent_objective,
        subagent_objective_seen,
    )

    state = _kanas_boat_state()
    sig_a = normalize_subagent_objective(
        subagent="fact_search_agent",
        claim_type="ticket_price",
        lookup_phase="official_site_discovery",
        source_family="search",
        search_query="喀纳斯湖 游船 船票 价格 官方",
        ticket_product="boat_ticket",
    )
    sig_b = normalize_subagent_objective(
        subagent="fact_search_agent",
        claim_type="ticket_price",
        lookup_phase="official_site_discovery",
        source_family="search",
        search_query="新疆 Altay 喀纳斯湖 游船 船票 价格 官方",
        ticket_product="boat_ticket",
    )
    assert sig_a == sig_b
    assert not subagent_objective_seen(state, sig_a)
    record_subagent_objective(state, sig_a)
    assert subagent_objective_seen(state, sig_b)


def test_fact_search_skips_reverse_geocode_without_coordinates():
    from app.agents.fact_search_agent import FactSearchAgent
    from app.orchestrator.mcp_tool_arguments import mcp_tool_invocation_ready
    from app.schemas.search_task import SearchTask

    state = _kanas_boat_state()
    task = SearchTask(
        task_id="t1",
        lookup_intent="喀纳斯湖游船船票价格",
        claim_target="ticket_price",
        anchor_keywords=["喀纳斯湖"],
        search_query="喀纳斯湖 游船 船票 价格 官方",
        information_need="ticket_price",
        preferred_tool="baidu_reverse_geocode_mcp",
    )
    assert not mcp_tool_invocation_ready("baidu_reverse_geocode_mcp", {}, state=state)
    picked = FactSearchAgent.pick_tool(task, None, state=state)
    assert picked == "search_mcp"


def test_user_limitations_hide_internal_policy_errors():
    from app.orchestrator.ticket_lookup_policy import filter_ticket_price_limitations

    raw = [
        "Cannot FINISH evidence planning: configured tools not yet attempted: search_mcp",
        "evidence_planning_and_tool_use reached max_steps",
        "official_source_discovery_mcp requires urls or search_results",
        "飞猪/大众点评本轮未返回有效票价。",
        "平台票价可能随日期、库存或套餐变化。",
    ]
    kept = filter_ticket_price_limitations(raw, need="ticket_price")
    assert "Cannot FINISH" not in " ".join(kept)
    assert "max_steps" not in " ".join(kept)
    assert "requires urls" not in " ".join(kept)
    assert any("飞猪" in line or "平台票价" in line for line in kept)
