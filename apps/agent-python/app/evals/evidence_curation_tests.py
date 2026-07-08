"""Tests for S7 evidence curation (filter, brief, residual isolation)."""

import asyncio

from app.agents.claim_relevance_filter_agent import ClaimRelevanceFilterAgent
from app.orchestrator.evidence_brief_builder import apply_evidence_brief, build_evidence_brief
from app.orchestrator.user_need_residual import attach_user_need_residual
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_brief import CuratedClaimRow, EvidenceBrief
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_need_residual import ResidualInformationNeed, UserNeedResidual
from app.schemas.user_query import TravelAgentState


def _miss_evidence(place: str, query: str) -> Evidence:
    return Evidence(
        evidence_id=f"miss-{query[:12]}",
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        country="China",
        place_name=place,
        confidence=0.4,
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value=f"No search hits for: {query}",
                confidence=0.4,
            )
        ],
    )


def _ticket_evidence() -> Evidence:
    return Evidence(
        evidence_id="ev-ticket",
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://example.com/ticket",
        country="China",
        place_name="巴音布鲁克景区",
        confidence=0.5,
        claims=[
            Claim(
                claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                value="成人票约65元（检索摘要，未核实）",
                confidence=0.5,
            )
        ],
    )


def test_filter_excludes_search_miss_values():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="巴音布鲁克门票",
        evidence=[
            _miss_evidence("巴音布鲁克景区", "巴音布鲁克 门票"),
            _ticket_evidence(),
        ],
        user_need_residual=UserNeedResidual(
            intent_summary="查询门票",
            task_family="fact_lookup",
            information_needs=[ResidualInformationNeed(need_type="ticket_price", priority="high")],
        ),
    )
    result = asyncio.get_event_loop().run_until_complete(
        ClaimRelevanceFilterAgent(llm_client=None).run(state)
    )
    curated = result["curated_claims"]
    assert len(curated) == 1
    assert curated[0]["claim_type"] == ClaimType.TICKET_PRICE_CANDIDATE.value
    assert "No search hits" not in curated[0]["value"]
    assert result["excluded_evidence_ids"]


def test_build_evidence_brief_from_structured_curated_claims():
    row = CuratedClaimRow(
        claim_type="ticket_price_candidate",
        value="65元",
        evidence_id="ev-ticket",
        source_name="open-webSearch",
        confidence=0.5,
        relevance_score=0.8,
        place_name="巴音布鲁克景区",
    )
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="门票",
        structured_result={"curated_claims": [row.model_dump()]},
    )
    brief = build_evidence_brief(state, "巴音布鲁克景区")
    assert brief.curated_claims
    assert brief.overall_confidence > 0
    apply_evidence_brief(state, brief)
    assert state.evidence_brief is not None
    assert state.field_evidence_summary


def test_curation_uses_need_residual_not_raw_query():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="用户声称门票免费",
        semantic_frame=SemanticFrame(
            raw_query="用户声称门票免费",
            task_family=TaskFamily.FACT_LOOKUP,
            decision_type=DecisionType.FACT_LOOKUP,
            entities=SemanticEntities(places=["某景区"]),
            information_needs=["ticket_price"],
        ),
        evidence=[_ticket_evidence()],
    )
    attach_user_need_residual(state)
    assert "免费" not in state.user_need_residual.model_dump_json()
    filtered = asyncio.get_event_loop().run_until_complete(
        ClaimRelevanceFilterAgent(llm_client=None).run(state)
    )
    assert filtered["curated_claims"]


def test_evidence_brief_to_field_summary():
    brief = EvidenceBrief(
        target_label="测试",
        curated_claims=[
            CuratedClaimRow(
                claim_type="ticket_price_candidate",
                value="10元",
                evidence_id="e1",
                source_name="src",
                confidence=0.6,
                relevance_score=0.7,
            )
        ],
        overall_confidence=0.42,
    )
    rows = brief.to_field_evidence_summary()
    assert rows[0]["field"] == "ticket_price_candidate"
    assert rows[0]["confidence"] == 0.6


def test_brief_derived_from_evidence_decision_report():
    from app.orchestrator.evidence_brief_builder import build_evidence_brief_from_report
    from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport

    ev = _ticket_evidence()
    report = EvidenceDecisionReport(
        claim_decisions=[
            ClaimDecision(
                claim_type="ticket_price",
                adoption="candidate_only",
                coverage_quality="partial",
                confidence=0.45,
                adopted_evidence_ids=[ev.evidence_id],
                reason="platform candidate",
            )
        ],
        overall_confidence=0.45,
    )
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="门票",
        evidence=[ev],
        evidence_decision_report=report,
    )
    brief = build_evidence_brief_from_report(state, report, target_label="巴音布鲁克景区")
    assert brief.curated_claims
    assert brief.curated_claims[0].claim_type == "ticket_price"
    assert brief.overall_confidence == 0.45
    assert any("ticket_price" in g for g in brief.coverage_gaps)
