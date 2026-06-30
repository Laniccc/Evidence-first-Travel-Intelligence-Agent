"""Phase 3 — official candidate bridge, page-reader URL wiring, S8 adoption constraints."""

from __future__ import annotations

from app.agents.fact_lookup_phase_runner import _has_url_inputs
from app.orchestrator.claim_decision_enrichment import enrich_claim_decision
from app.orchestrator.fact_lookup_guided_composition import (
    build_fact_lookup_draft,
    build_fact_lookup_presentation,
)
from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments
from app.orchestrator.official_candidate_bridge import (
    collect_readable_urls_for_claim,
    sync_official_candidates_to_structured,
)
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.official_source import (
    OfficialSourceCandidate,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
)
from app.schemas.response_contract import ResponseContract
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from app.orchestrator.response_contract_compiler import ResponseContractCompiler


def _opening_hours_state(*, evidence: list | None = None) -> TravelAgentState:
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
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    if evidence is not None:
        state.evidence = list(evidence)
    return state


def _discovery_evidence() -> Evidence:
    cand = OfficialSourceCandidate(
        url="https://www.dpm.org.cn/",
        domain="dpm.org.cn",
        title="故宫博物院",
        source_class=SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
        official_confidence=0.92,
        has_opening_hours=True,
        supports_claim_types=["opening_hours"],
        claim_relevance_hints={"opening_hours": 0.9},
    )
    return Evidence(
        evidence_id="ev-discovery",
        source_name="Official Source Discovery",
        source_type=SourceType.WEB,
        source_url="https://www.dpm.org.cn/",
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                value="Official source candidate",
                normalized_value=cand.model_dump(),
                confidence=0.92,
            )
        ],
        confidence=0.92,
    )


def test_sync_official_candidates_to_structured():
    state = _opening_hours_state(evidence=[_discovery_evidence()])
    sync_official_candidates_to_structured(state)
    rows = (state.structured_result or {}).get("official_source_candidates") or []
    assert rows
    assert rows[0]["url"] == "https://www.dpm.org.cn/"
    assert rows[0]["source_class"] == SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL


def test_collect_readable_urls_forbidden_city_whitelist():
    state = _opening_hours_state()
    urls = collect_readable_urls_for_claim(state, "opening_hours")
    assert urls
    assert any("dpm.org.cn" in u for u in urls)


def test_mcp_tool_arguments_opening_hours_uses_whitelist_and_follow():
    state = _opening_hours_state()
    args = enrich_mcp_tool_arguments("official_page_reader_mcp", {}, state=state)
    assert args.get("information_need") == "opening_hours"
    assert int(args.get("max_follow_urls") or 0) >= 4
    assert "dpm.org.cn" in str(args.get("url") or "")


def test_has_url_inputs_with_whitelist_only():
    state = _opening_hours_state()
    assert _has_url_inputs(state)


def test_adoption_compose_instructions_candidate_only():
    state = _opening_hours_state()
    state.evidence_decision_report = type(
        "R",
        (),
        {
            "claim_decisions": [
                enrich_claim_decision(
                    ClaimDecision(
                        claim_type="opening_hours",
                        adoption="candidate_only",
                        coverage_quality="partial",
                    )
                )
            ]
        },
    )()
    presentation = build_fact_lookup_presentation(state)
    joined = " ".join(presentation.get("compose_instructions") or [])
    assert "candidate_only" in joined
    assert "不得写成定论" in joined or "官方未确认" in joined


def test_visit_html_official_evidence_strong_draft_contains_hours():
    html = """
    <div>4月1日至10月31日开放时间</div>
    <div class="li">开放入馆时间：<span>8:30</span></div>
    <div class="li">停止入馆时间：<span>16:00</span></div>
    <div class="li">闭馆时间：<span>17:00</span></div>
    """
    from tools.mcp.adapters.page_content_extractor import build_page_evidence

    official_ev = build_page_evidence(
        source_name="Official Page (fetch-web)",
        source_url="https://www.dpm.org.cn/Visit.html",
        text=html,
        country="China",
        city="北京",
        place_name="故宫博物院",
        information_need="opening_hours",
    )
    state = _opening_hours_state(evidence=[official_ev])
    decision = enrich_claim_decision(
        ClaimDecision(
            claim_type="opening_hours",
            adoption="adopt",
            coverage_quality="strong",
            adopted_evidence_ids=[official_ev.evidence_id],
        ),
        evidence=[official_ev],
    )
    state.evidence_decision_report = type("R", (), {"claim_decisions": [decision]})()
    draft = build_fact_lookup_draft(state)
    body = " ".join(b for sec in draft.sections for b in (sec.bullets or []))
    assert "8:30" in body
    assert decision.adoption_level == "strong"
