"""Unit tests for official source discovery and S7 judgement (no LLM / external IO)."""

from __future__ import annotations

import asyncio
import json

from app.orchestrator.evidence_evaluator import evaluate_evidence
from app.orchestrator.evidence_gap_planner import EvidenceGapPlanner
from app.orchestrator.official_source_judgement import (
    best_official_support,
    judge_candidate_for_claim,
    needs_official_source_gap,
)
from app.orchestrator.claim_policy_registry import resolve_policy
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.evidence_gap_request import EvidenceGapLoopState
from app.schemas.official_source import (
    OfficialSourceCandidate,
    SOURCE_CLASS_OFFICIAL_GOVERNMENT,
    SOURCE_CLASS_OTA_PLATFORM,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
    SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE,
)
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState
from tools.official_source.official_source_classifier import OfficialSourceClassifier
from tools.official_source.official_source_discovery_tool import OfficialSourceDiscoveryTool

SEARCH_FIXTURE = [
    {
        "url": "https://www.lijiang.gov.cn/zwgk/whly/2020/1201/12345.html",
        "title": "束河古镇文化遗产保护",
        "snippet": "束河古镇是丽江世界文化遗产的重要组成部分。",
    },
    {
        "url": "https://you.ctrip.com/sight/lijiang/123.html",
        "title": "束河古镇门票预订",
        "snippet": "门票参考价70元，开放时间全天。",
    },
    {
        "url": "https://www.sogou.com/link?url=abc",
        "title": "束河古镇攻略",
        "snippet": "门票70元，建议网上预订。",
    },
]


def _candidate_evidence(cand: OfficialSourceCandidate, evidence_id: str = "ev-official-1") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_name="Official Source Discovery",
        source_type=SourceType.WEB,
        country="China",
        place_name="束河古镇",
        confidence=cand.official_confidence,
        claims=[
            Claim(
                claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                value=f"candidate {cand.source_class}",
                normalized_value=cand.model_dump(),
                confidence=cand.official_confidence,
            )
        ],
    )


def test_official_source_classifier_scores_government_domain():
    clf = OfficialSourceClassifier()
    cand = clf.classify(
        "https://www.lijiang.gov.cn/zwgk/whly/",
        title="丽江市人民政府 束河古镇",
        snippet="文化遗产保护",
        place_name="束河古镇",
    )
    assert cand.source_class in {SOURCE_CLASS_OFFICIAL_GOVERNMENT, "tourism_board_official"}
    assert cand.official_confidence >= 0.65


def test_official_source_classifier_rejects_ota_as_official():
    clf = OfficialSourceClassifier()
    cand = clf.classify(
        "https://you.ctrip.com/sight/lijiang/123.html",
        title="束河古镇门票预订",
        snippet="门票70元",
        place_name="束河古镇",
    )
    assert cand.source_class == SOURCE_CLASS_OTA_PLATFORM
    assert cand.official_confidence < 0.65


def test_official_source_candidate_does_not_cover_ticket_without_price():
    cand = OfficialSourceCandidate(
        url="https://www.lijiang.gov.cn/",
        domain="lijiang.gov.cn",
        source_class=SOURCE_CLASS_OFFICIAL_GOVERNMENT,
        official_confidence=0.9,
        has_ticket_info=False,
        claim_relevance_hints={"ticket_price": 0.2},
    )
    result = judge_candidate_for_claim(cand, "ticket_price")
    assert result.coverage_tier in {"weak", "none"}


def test_official_source_with_price_covers_ticket_price_strong():
    cand = OfficialSourceCandidate(
        url="https://shuxihe-scenic.cn/ticket",
        domain="shuxihe-scenic.cn",
        source_class=SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
        official_confidence=0.88,
        has_ticket_info=True,
        claim_relevance_hints={"ticket_price": 0.92},
    )
    result = judge_candidate_for_claim(cand, "ticket_price")
    assert result.coverage_tier == "strong"


def test_government_background_does_not_cover_ticket_price():
    cand = OfficialSourceCandidate(
        url="https://www.lijiang.gov.cn/heritage",
        domain="lijiang.gov.cn",
        source_class=SOURCE_CLASS_OFFICIAL_GOVERNMENT,
        official_confidence=0.9,
        has_ticket_info=False,
        has_about_or_footer_info=True,
        claim_relevance_hints={"destination_background": 0.9, "ticket_price": 0.2},
    )
    support = best_official_support([_candidate_evidence(cand)], "ticket_price")
    assert support.tier in {"weak", "none"}


def test_s7_generates_gap_when_only_platform_ticket_candidate():
    clf = OfficialSourceClassifier()
    ota = clf.classify(
        SEARCH_FIXTURE[1]["url"],
        title=SEARCH_FIXTURE[1]["title"],
        snippet=SEARCH_FIXTURE[1]["snippet"],
        place_name="束河古镇",
    )
    evidence = [_candidate_evidence(ota)]
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="束河古镇门票多少钱",
        semantic_frame=SemanticFrame(
            raw_query="束河古镇门票多少钱",
            normalized_request="束河古镇门票多少钱",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", city="丽江", places=["束河古镇"]),
        ),
        response_contract=ResponseContract(
            claim_requirements=[
                ClaimRequirement(
                    claim_type="ticket_price",
                    claim_family="ticket_booking",
                    claim_description="门票价格",
                    priority="required",
                    preferred_tools=["search_mcp", "official_source_discovery_mcp"],
                )
            ]
        ),
        evidence=evidence,
        gap_loop_state=EvidenceGapLoopState(max_gap_rounds=1),
    )
    report = evaluate_evidence(state, target_label="束河古镇")
    ticket_decision = next(d for d in report.claim_decisions if d.claim_type == "ticket_price")
    assert ticket_decision.adoption in {"candidate_only", "refuse_to_guess", "adopt_with_limitation"}
    assert needs_official_source_gap(evidence, "ticket_price", ticket_decision)

    claim = state.response_contract.claim_requirements[0]
    policy = resolve_policy(claim)
    gap = EvidenceGapPlanner().plan_gaps(
        state,
        claim,
        policy,
        ticket_decision,
        gap_round=0,
        max_gap_rounds=1,
    )
    assert gap is not None
    assert "official_source_discovery_mcp" in gap.suggested_tools


def test_hits_from_evidence_parses_search_snippet_title():
    from tools.official_source.url_normalizer import hits_from_evidence_list

    ev = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://www.sogou.com/link?url=abc",
        country="China",
        place_name="故宫博物院",
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value="导览 - 故宫博物院: 开馆时间为8:30,停止入馆时间为16:00,闭馆时间为17:00。",
                raw_text="导览 - 故宫博物院: 开馆时间为8:30,停止入馆时间为16:00,闭馆时间为17:00。",
                confidence=0.5,
            )
        ],
    )
    hits = hits_from_evidence_list([ev])
    assert hits
    assert "导览" in (hits[0].get("title") or "")
    assert "8:30" in (hits[0].get("snippet") or "")


def test_discovery_collects_whitelist_and_search_hits():
    tool = OfficialSourceDiscoveryTool()
    hits = tool._collect_hits(
        {
            "place_name": "故宫博物院",
            "search_results": [
                {"task_id": "search-1", "search_query": "故宫 开放时间", "evidence_count": 5},
                {
                    "url": "https://www.sogou.com/link?url=x",
                    "title": "导览 - 故宫博物院",
                    "snippet": "开馆时间为8:30,闭馆时间为17:00",
                },
            ],
            "prior_evidence": [],
        }
    )
    urls = [h.get("url") for h in hits]
    assert "https://www.dpm.org.cn/" in urls
    assert any("sogou.com" in (u or "") for u in urls)


def test_classifier_scores_redirect_official_guide_snippet():
    clf = OfficialSourceClassifier()
    cand = clf.classify(
        "https://www.sogou.com/link?url=abc",
        title="导览 - 故宫博物院",
        snippet="开馆时间为8:30,停止入馆时间为16:00,闭馆时间为17:00",
        place_name="故宫博物院",
        claim_type="opening_hours",
    )
    assert cand.has_opening_hours
    assert cand.source_class in {
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL_CANDIDATE,
        SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL,
    }
    support = judge_candidate_for_claim(cand, "opening_hours")
    assert support.coverage_tier in {"partial", "strong"}


async def _run_forbidden_city_discovery():
    tool = OfficialSourceDiscoveryTool()
    return await tool.run(
        place_name="故宫博物院",
        claim_type="opening_hours",
        city="北京",
        country="China",
        prior_evidence=[],
        search_results=[],
        probe_top_n=0,
    )


def test_forbidden_city_whitelist_yields_official_candidate():
    evidence = asyncio.run(_run_forbidden_city_discovery())
    assert evidence
    classes = []
    for ev in evidence:
        for claim in ev.claims:
            if isinstance(claim.normalized_value, dict):
                classes.append(claim.normalized_value.get("source_class"))
    assert SOURCE_CLASS_SCENIC_OPERATOR_OFFICIAL in classes


def test_claims_satisfy_need_rejects_nav_excerpt_fallback():
    from tools.official_source.official_page_follower import claims_satisfy_need

    nav_excerpt = Claim(
        claim_type=ClaimType.OPENING_HOURS,
        value='{"truncated": true, "preview": "首页 导览 开放时间 在线订票"}',
        confidence=0.55,
    )
    assert not claims_satisfy_need([nav_excerpt], "opening_hours")

    real_hours = Claim(
        claim_type=ClaimType.OPENING_HOURS,
        value="4月1日至10月31日: 开馆8:30，停止入馆16:00，闭馆17:00",
        confidence=0.72,
    )
    assert claims_satisfy_need([real_hours], "opening_hours")


def test_text_from_mcp_payload_unwraps_truncated_fetch_preview():
    from tools.mcp.adapters.page_content_extractor import text_from_mcp_payload

    payload = {
        "truncated": True,
        "preview": json.dumps(
            {
                "url": "https://www.dpm.org.cn/Visit.html",
                "content": "4月1日至10月31日开放时间 开馆8:30 停止入馆16:00",
            },
            ensure_ascii=False,
        ),
    }
    text = text_from_mcp_payload(payload)
    assert "8:30" in text
    assert "16:00" in text
    from tools.official_source.official_page_follower import plan_follow_urls

    urls = plan_follow_urls(
        "https://www.dpm.org.cn/",
        information_need="opening_hours",
        place_name="故宫博物院",
    )
    assert "https://www.dpm.org.cn/Visit.html" in urls


def test_extract_hours_from_dpm_visit_html_fixture():
    from tools.mcp.adapters.page_content_extractor import extract_claims_from_text
    from tools.official_source.official_page_follower import claims_satisfy_need

    html = """
    <div>4月1日至10月31日开放时间</div>
    <div class="list">
      <div class="li">开放入馆时间：<span>8:30</span></div>
      <div class="li">停止入馆时间：<span>16:00</span></div>
      <div class="li">闭馆时间：<span>17:00</span></div>
    </div>
    <div>11月1日至来年3月31日开放时间</div>
    <div class="list">
      <div class="li">开放入馆时间：<span>8:30</span></div>
      <div class="li">停止入馆时间：<span>15:30</span></div>
      <div class="li">闭馆时间：<span>16:30</span></div>
    </div>
    <p>除法定节假日，故宫博物院全年实行周一闭馆的措施。</p>
    """
    claims, _ = extract_claims_from_text(html, information_need="opening_hours")
    assert claims
    hours = next(c for c in claims if c.claim_type == ClaimType.OPENING_HOURS)
    assert "8:30" in hours.value
    assert "16:00" in hours.value
    assert "15:30" in hours.value
    assert "周一" in hours.value
    assert claims_satisfy_need(claims, "opening_hours")


def test_official_page_evidence_covers_opening_hours_strong():
    from app.orchestrator.evidence_evaluator import evaluate_evidence

    official_hours = Evidence(
        evidence_id="ev-official-hours",
        source_name="Official Page (fetch-web)",
        source_type=SourceType.OFFICIAL,
        source_url="https://www.dpm.org.cn/Visit.html",
        country="China",
        place_name="故宫博物院",
        confidence=0.85,
        claims=[
            Claim(
                claim_type=ClaimType.OPENING_HOURS,
                value="4月1日至10月31日: 开馆8:30，停止入馆16:00，闭馆17:00",
                confidence=0.85,
            )
        ],
    )
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="故宫博物院开放时间",
        semantic_frame=SemanticFrame(
            raw_query="故宫博物院开放时间",
            normalized_request="故宫博物院开放时间",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", city="北京", places=["故宫博物院"]),
        ),
        response_contract=ResponseContract(
            claim_requirements=[
                ClaimRequirement(
                    claim_type="opening_hours",
                    claim_family="operation_status",
                    claim_description="开放时间",
                    priority="required",
                    preferred_tools=["official_page_reader_mcp"],
                )
            ]
        ),
        evidence=[official_hours],
        gap_loop_state=EvidenceGapLoopState(max_gap_rounds=1),
    )
    report = evaluate_evidence(state, target_label="故宫博物院")
    decision = next(d for d in report.claim_decisions if d.claim_type == "opening_hours")
    assert decision.coverage_quality in {"partial", "strong"}
    assert decision.adoption in {"adopt", "adopt_with_limitation"}


async def _run_discovery():
    tool = OfficialSourceDiscoveryTool()
    return await tool.run(
        place_name="束河古镇",
        claim_type="ticket_price",
        city="丽江",
        country="China",
        search_results=SEARCH_FIXTURE,
        probe_top_n=0,
    )


def test_official_source_discovery_tool_normalizes_candidates():
    evidence = asyncio.run(_run_discovery())
    assert evidence
    classes = set()
    for ev in evidence:
        for claim in ev.claims:
            if claim.claim_type == ClaimType.OFFICIAL_SOURCE_CANDIDATE and isinstance(
                claim.normalized_value, dict
            ):
                classes.add(claim.normalized_value.get("source_class"))
    assert SOURCE_CLASS_OFFICIAL_GOVERNMENT in classes or "tourism_board_official" in classes
    assert SOURCE_CLASS_OTA_PLATFORM in classes
    has_redirect_signal = any(
        isinstance(c.normalized_value, dict)
        and "redirect_wrapper_url" in (c.normalized_value.get("negative_signals") or [])
        for ev in evidence
        for c in ev.claims
        if c.claim_type == ClaimType.OFFICIAL_SOURCE_CANDIDATE
    )
    assert has_redirect_signal or any(
        isinstance(c.normalized_value, dict)
        and c.normalized_value.get("source_class") == "seo_content_site"
        for ev in evidence
        for c in ev.claims
    )
