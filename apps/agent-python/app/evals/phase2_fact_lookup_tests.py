"""Phase 2 — opening hours extract, search snippet ladder, S7/S8 alignment."""

from __future__ import annotations

from app.orchestrator.claim_adoption_policy import ClaimAdoptionPolicy
from app.orchestrator.claim_decision_enrichment import enrich_claim_decision
from app.orchestrator.evidence_usage_role import infer_evidence_usage_role, is_entity_anchor_only
from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft
from app.orchestrator.opening_hours_extractor import extract_opening_hours_from_text
from app.orchestrator.search_snippet_policy import evidence_strength_for_claim, is_search_snippet_evidence
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from app.orchestrator.response_contract_compiler import ResponseContractCompiler


def test_opening_hours_extractor_parses_times():
    fact = extract_opening_hours_from_text(
        "故宫博物院开放时间 8:30-17:00，周一闭馆，4月1日-10月31日旺季"
    )
    assert fact is not None
    assert fact.open_time == "8:30"
    assert fact.close_time == "17:00"
    assert any("周一" in d for d in fact.closed_days)


def test_search_snippet_is_candidate_only_for_ticket():
    ev = Evidence(
        evidence_id="ev-snippet",
        source_name="search_mcp",
        source_type=SourceType.WEB,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                value="喀纳斯湖门票 150 元/人 旅行社",
                confidence=0.4,
            )
        ],
        confidence=0.4,
    )
    assert is_search_snippet_evidence(ev)
    assert evidence_strength_for_claim(ev, "ticket_price") == "candidate_only"


def test_map_poi_is_entity_anchor_only_not_claim_support():
    ev = Evidence(
        evidence_id="ev-map",
        source_name="baidu_place_search_mcp",
        source_type=SourceType.MAP,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value="故宫博物院-午门",
                confidence=0.7,
            )
        ],
        confidence=0.7,
    )
    role = infer_evidence_usage_role(ev, "opening_hours")
    assert role.entity_anchor
    assert not role.claim_support
    assert is_entity_anchor_only(ev, "opening_hours")


def test_ticket_third_party_snippet_adoption_candidate_only():
    ev = Evidence(
        evidence_id="ev1",
        source_name="search_mcp",
        source_type=SourceType.WEB,
        country="China",
        claims=[Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="150元/人", confidence=0.5)],
        confidence=0.5,
    )
    from app.orchestrator.evidence_scorer import EvidenceScore

    scores = [
        EvidenceScore(
            evidence_id="ev1",
            claim_type="ticket_price",
            claim_value="150元/人",
            source_name="search_mcp",
            source_type="web",
            source_reliability=0.5,
            total_score=0.6,
            claim_relevance=0.6,
            claim_support=0.5,
            freshness=0.5,
            specificity=0.5,
            tool_success=1.0,
            rank_reason="ticket_price",
        )
    ]
    adoption = ClaimAdoptionPolicy()._ticket_price_adoption(
        scores, "partial", "adopt", evidence=[ev]
    )
    assert adoption == "candidate_only"


def test_claim_decision_enrichment_candidate_cannot_answer_directly():
    decision = enrich_claim_decision(
        ClaimDecision(
            claim_type="ticket_price",
            coverage_quality="partial",
            adoption="candidate_only",
            adopted_evidence_ids=["ev1"],
        ),
        evidence=[
            Evidence(
                evidence_id="ev1",
                source_name="search",
                source_type=SourceType.WEB,
                country="China",
                claims=[Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="150元", confidence=0.4)],
                confidence=0.4,
            )
        ],
    )
    assert decision.adoption_level == "candidate_only"
    assert not decision.can_answer_directly
    assert decision.must_show_limitation


def test_s8_candidate_only_ticket_does_not_state_as_official_price():
    frame = SemanticFrame(
        raw_query="喀纳斯湖游船船票多少钱？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["喀纳斯湖"]),
        information_needs=["ticket_price"],
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
    state.evidence_decision_report = type(
        "R",
        (),
        {
            "claim_decisions": [
                enrich_claim_decision(
                    ClaimDecision(
                        claim_type="ticket_price",
                        adoption="candidate_only",
                        coverage_quality="partial",
                        adopted_evidence_ids=["ev1"],
                        adopted_value="150元/人",
                    )
                )
            ]
        },
    )()
    draft = build_fact_lookup_draft(state)
    body = " ".join(
        b for sec in draft.sections for b in (sec.bullets or [])
    )
    assert "不能作为结论" in body or "未能验证" in body or "未查到可采纳" in body
