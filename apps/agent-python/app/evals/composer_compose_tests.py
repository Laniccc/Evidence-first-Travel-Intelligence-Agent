"""Unit tests for S8 AnswerComposerAgent (LLM path, no static fallback)."""

import asyncio
import json

from app.agents.answer_composer_agent import AnswerComposerAgent
from app.agents.composer_agent import ComposerAgent
from app.evals.llm_test_helpers import StubLLMClient
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_brief import CuratedClaimRow, EvidenceBrief
from app.schemas.final_answer_draft import FinalAnswerDraft, FinalAnswerSection
from app.schemas.user_need_residual import ResidualInformationNeed, UserNeedResidual
from app.schemas.user_query import TravelAgentState
from app.schemas.tool_trace import ToolTrace


def _miss_evidence(query: str) -> Evidence:
    return Evidence(
        evidence_id=f"miss-{hash(query) % 10000}",
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        country="China",
        city="南京",
        place_name="南京博物院",
        confidence=0.4,
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value=f"No search hits for: {query}",
                confidence=0.4,
            )
        ],
    )


def _composer_stub_response(bundle: dict) -> str:
    target = bundle.get("target_label", "目的地")
    claims = bundle.get("curated_claims") or bundle.get("actionable_evidence_claims") or []
    bullets = []
    cited = []
    for c in claims[:3]:
        conf = c.get("confidence", 0.5)
        bullets.append(f"{c.get('value')}（置信度 {conf:.0%}）")
        if c.get("evidence_id"):
            cited.append(c["evidence_id"])
    if not bullets:
        bullets.append("未能从检索获得足够官方信息，建议出发前再确认。")
    low_conf = float(bundle.get("overall_confidence", 0))
    conclusion = f"关于{target}：{'；'.join(bullets)}。建议出发前再核实官方渠道。"
    if low_conf < 0.55:
        conclusion = f"【证据不足/未核实】{conclusion}"
    return json.dumps(
        {
            "headline": f"关于 {target}",
            "conclusion": conclusion,
            "sections": [{"title": "检索线索", "bullets": bullets}],
            "limitations": bundle.get("limitations", []),
            "cited_evidence_ids": cited,
            "answer_text": conclusion,
            "compose_mode": bundle.get("compose_mode", "advisory"),
        },
        ensure_ascii=False,
    )


def test_compose_suitability_skips_search_miss_sentinels():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="南京博物院适合带父母去吗",
        evidence=[
            _miss_evidence("南京博物院 人多吗 拥挤"),
            _miss_evidence("南京博物院 老人 游览 体验"),
        ],
        tool_traces=[
            ToolTrace(
                tool_name="search_mcp",
                input={"query": "南京博物院 人多吗 拥挤"},
                status="ok",
            )
        ],
        limitations=["关键证据不足，部分结论置信度受限。"],
        evidence_brief=EvidenceBrief(
            target_label="南京博物院",
            overall_confidence=0.3,
            coverage_gaps=["crowd_level uncovered"],
        ),
    )
    text = ComposerAgent.compose_suitability("南京博物院", state.evidence, state)
    assert "No search hits" not in text
    assert "通车" not in text
    assert "适合带父母" in text


def test_compose_fact_lookup_shows_clues_with_confidence():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="巴音布鲁克景区需要门票吗",
        evidence=[
            Evidence(
                evidence_id="ev1",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                source_url="https://example.com/ticket",
                country="China",
                place_name="巴音布鲁克景区",
                confidence=0.5,
                claims=[
                    Claim(
                        claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                        value="巴音布鲁克草原门票：成人票约65元（检索摘要）",
                        confidence=0.5,
                    )
                ],
            )
        ],
        tool_traces=[
            ToolTrace(
                tool_name="search_mcp",
                input={"query": "巴音布鲁克景区门票价格"},
                status="ok",
            )
        ],
    )
    text = ComposerAgent.compose_fact_lookup("巴音布鲁克景区", state.evidence, state)
    assert "置信度" in text
    assert "65元" in text
    assert "No search hits" not in text


def test_looks_incomplete_answer_rejects_truncated_llm_text():
    draft = FinalAnswerDraft(
        answer_text="关于巴音布鲁克景区是否需要门票的问题，目前没有找到确切的官方",
    )
    assert AnswerComposerAgent._looks_incomplete_answer(draft) is True


def test_looks_incomplete_answer_rejects_truncated_section_bullet():
    draft = FinalAnswerDraft(
        conclusion="结论完整。",
        sections=[
            FinalAnswerSection(
                title="禾木村",
                bullets=["据部分游记描述，禾木村长期保持原始状态，有"],
            )
        ],
    )
    assert AnswerComposerAgent._looks_incomplete_answer(draft) is True


def test_summarize_comparison_claims_for_compose_limits_payload():
    from app.orchestrator.comparison_helpers import summarize_comparison_claims_for_compose

    claims = [
        {
            "place_name": "禾木村",
            "claim_type": "review_summary",
            "value": "a" * 300,
            "confidence": 0.8,
            "relevance_score": 0.9,
            "evidence_id": "e1",
        },
        {
            "place_name": "禾木村",
            "claim_type": "review_summary",
            "value": "second",
            "confidence": 0.6,
            "relevance_score": 0.5,
            "evidence_id": "e2",
        },
        {
            "place_name": "喀纳斯景区",
            "claim_type": "crowd_level",
            "value": "旺季游客较多",
            "confidence": 0.7,
            "relevance_score": 0.8,
            "evidence_id": "e3",
        },
    ]
    out = summarize_comparison_claims_for_compose(claims, ["禾木村", "喀纳斯景区"])
    assert len(out) <= 6
    assert all(len(str(c["value"])) <= 220 for c in out)


def test_comparison_fallback_accepted_with_headline_title():
    bundle = {
        "compose_mode": "compare",
        "target_label": "禾木村 vs 喀纳斯景区",
        "compare_place_names": ["禾木村", "喀纳斯景区"],
        "overall_confidence": 0.43,
        "evidence_ids": ["e1", "e2"],
        "has_actionable_evidence": True,
        "actionable_evidence_claims": [
            {
                "place_name": "禾木",
                "claim_type": "review_summary",
                "value": "秋色很美，适合摄影",
                "confidence": 0.7,
                "evidence_id": "e1",
            },
            {
                "place_name": "喀纳斯",
                "claim_type": "crowd_level",
                "value": "旺季拥挤但风景值得",
                "confidence": 0.6,
                "evidence_id": "e2",
            },
        ],
    }
    draft = AnswerComposerAgent._comparison_fallback_draft(bundle)
    agent = AnswerComposerAgent()
    assert agent._looks_incomplete_answer(draft) is False
    assert agent._accept_draft(draft, bundle) is True


def test_comparison_fallback_draft_per_place_sections():
    bundle = {
        "compose_mode": "compare",
        "target_label": "禾木村 vs 喀纳斯景区",
        "compare_place_names": ["禾木村", "喀纳斯景区"],
        "overall_confidence": 0.43,
        "actionable_evidence_claims": [
            {
                "place_name": "禾木村",
                "claim_type": "review_summary",
                "value": "秋色很美",
                "confidence": 0.7,
                "evidence_id": "e1",
            },
            {
                "place_name": "喀纳斯景区",
                "claim_type": "crowd_level",
                "value": "旺季拥挤",
                "confidence": 0.6,
                "evidence_id": "e2",
            },
        ],
    }
    draft = AnswerComposerAgent._comparison_fallback_draft(bundle)
    assert len(draft.sections) == 2
    assert draft.answer_text.endswith("。") or "。" in draft.answer_text


def test_validate_draft_allows_gap_answer_without_citations():
    bundle = {
        "evidence_ids": ["e1"],
        "evidence_claims": [
            {
                "evidence_id": "e1",
                "value": "No search hits for: foo",
                "is_search_miss": True,
            }
        ],
        "has_actionable_evidence": False,
    }
    draft = FinalAnswerDraft(
        conclusion="未能从检索获得足够信息，建议出发前确认官方公告。",
        cited_evidence_ids=[],
    )
    agent = AnswerComposerAgent()
    assert agent._validate_draft(draft, bundle) is True


def test_llm_compose_uses_brief_and_low_confidence_disclaimer():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="巴音布鲁克门票多少钱",
        evidence=[
            Evidence(
                evidence_id="ev-ticket",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="巴音布鲁克景区",
                confidence=0.5,
                claims=[
                    Claim(
                        claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                        value="成人票约65元（检索摘要）",
                        confidence=0.5,
                    )
                ],
            )
        ],
        user_need_residual=UserNeedResidual(
            intent_summary="查询门票价格",
            task_family="fact_lookup",
            information_needs=[ResidualInformationNeed(need_type="ticket_price")],
        ),
        evidence_brief=EvidenceBrief(
            target_label="巴音布鲁克景区",
            curated_claims=[
                CuratedClaimRow(
                    claim_type="ticket_price_candidate",
                    value="成人票约65元（检索摘要）",
                    evidence_id="ev-ticket",
                    source_name="open-webSearch",
                    confidence=0.5,
                    relevance_score=0.8,
                    place_name="巴音布鲁克景区",
                )
            ],
            overall_confidence=0.4,
        ),
    )

    def responder(system: str, user: str) -> str:
        bundle = json.loads(user)
        return _composer_stub_response(bundle)

    agent = AnswerComposerAgent(StubLLMClient(responder))
    draft = asyncio.run(
        agent.compose(state, {"compose_mode": "fact_lookup", "target_label": "巴音布鲁克景区"})
    )
    assert "65元" in draft.answer_text
    assert "证据不足" in draft.answer_text or "置信度" in draft.answer_text
    assert "No search hits" not in draft.answer_text


def test_infrastructure_error_when_llm_unavailable():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")

    class NoLLM:
        def _should_use_anthropic(self) -> bool:
            return False

    draft = asyncio.run(
        AnswerComposerAgent(NoLLM()).compose(state, {"target_label": "测试地"})
    )
    assert "合成服务不可用" in draft.answer_text
    assert "No search hits" not in draft.answer_text


def test_normalize_truncated_uuid_prefix():
    full_id = "7a3a8fc7-1234-5678-9abc-def012345678"
    resolved, unresolved = AnswerComposerAgent._normalize_cited_evidence_ids(
        ["7a3a8fc7"],
        [full_id],
    )
    assert resolved == [full_id]
    assert unresolved == []


def test_normalize_draft_payload_dict_bullets():
    eid = "a1b2c3d4-958d-9489-227e6cb19091"
    raw = {
        "headline": "门票",
        "conclusion": "有线索显示需购票。",
        "sections": [
            {
                "title": "检索线索",
                "bullets": [
                    {"content": "有线索称门票约40元", "evidence_id": eid},
                    "纯字符串 bullet",
                ],
            }
        ],
        "cited_evidence_ids": [],
    }
    normalized = AnswerComposerAgent._normalize_draft_payload(raw)
    draft = FinalAnswerDraft.model_validate(normalized)
    assert draft.sections[0].bullets == ["有线索称门票约40元", "纯字符串 bullet"]
    assert eid in draft.cited_evidence_ids


def test_postprocess_resolves_truncated_citations_in_draft():
    full_id = "7a3a8fc7-1234-5678-9abc-def012345678"
    bundle = {
        "evidence_ids": [full_id],
        "has_actionable_evidence": True,
        "actionable_evidence_claims": [
            {
                "evidence_id": full_id,
                "value": "门票约75元",
                "confidence": 0.6,
            }
        ],
    }
    draft = FinalAnswerDraft(
        conclusion="检索显示门票约75元，建议核实官方渠道。",
        cited_evidence_ids=["7a3a8fc7"],
    )
    agent = AnswerComposerAgent()
    draft, note = agent._postprocess_draft(draft, bundle)
    assert draft.cited_evidence_ids == [full_id]
    assert note is not None
    assert agent._validate_draft(draft, bundle) is True


def test_infer_citations_when_llm_omits_ids():
    full_id = "ev-ticket-full-uuid-0001"
    bundle = {
        "evidence_ids": [full_id],
        "has_actionable_evidence": True,
        "actionable_evidence_claims": [
            {
                "evidence_id": full_id,
                "value": "成人票约65元（检索摘要）",
                "confidence": 0.5,
            }
        ],
    }
    draft = FinalAnswerDraft(
        conclusion="成人票约65元（检索摘要），建议出发前核实。",
        cited_evidence_ids=[],
    )
    agent = AnswerComposerAgent()
    draft, note = agent._postprocess_draft(draft, bundle)
    assert full_id in draft.cited_evidence_ids
    assert agent._validate_draft(draft, bundle) is True


def test_llm_truncated_uuid_compose_succeeds():
    full_id = "7a3a8fc7-abcd-ef01-2345-6789abcdef01"
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="五彩滩门票多少钱",
        evidence=[
            Evidence(
                evidence_id=full_id,
                source_name="ctrip",
                source_type=SourceType.WEB,
                country="China",
                place_name="五彩滩",
                confidence=0.6,
                claims=[
                    Claim(
                        claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                        value="门票约75元",
                        confidence=0.6,
                    )
                ],
            )
        ],
        evidence_brief=EvidenceBrief(
            target_label="五彩滩",
            curated_claims=[
                CuratedClaimRow(
                    claim_type="ticket_price_candidate",
                    value="门票约75元",
                    evidence_id=full_id,
                    source_name="ctrip",
                    confidence=0.6,
                    relevance_score=0.9,
                    place_name="五彩滩",
                )
            ],
            overall_confidence=0.6,
        ),
    )

    def responder(system: str, user: str) -> str:
        return json.dumps(
            {
                "headline": "关于 五彩滩",
                "conclusion": "检索显示五彩滩门票约75元，建议核实官方渠道后出行。",
                "sections": [{"title": "门票", "bullets": ["门票约75元（置信度 60%）"]}],
                "limitations": [],
                "cited_evidence_ids": ["7a3a8fc7"],
                "answer_text": "检索显示五彩滩门票约75元，建议核实官方渠道后出行。",
                "compose_mode": "fact_lookup",
            },
            ensure_ascii=False,
        )

    agent = AnswerComposerAgent(StubLLMClient(responder))
    draft = asyncio.run(
        agent.compose(state, {"compose_mode": "fact_lookup", "target_label": "五彩滩"})
    )
    assert "75元" in draft.answer_text
    assert draft.cited_evidence_ids == [full_id]
    assert "合成服务不可用" not in draft.answer_text


def test_evidence_fallback_when_llm_repeatedly_invalid():
    full_id = "ticket-ev-uuid-9999"
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="门票",
        evidence=[
            Evidence(
                evidence_id=full_id,
                source_name="ctrip",
                source_type=SourceType.WEB,
                country="China",
                place_name="五彩滩",
                confidence=0.6,
                claims=[
                    Claim(
                        claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                        value="门票约50元",
                        confidence=0.6,
                    )
                ],
            )
        ],
        evidence_brief=EvidenceBrief(
            target_label="五彩滩",
            curated_claims=[
                CuratedClaimRow(
                    claim_type="ticket_price_candidate",
                    value="门票约50元",
                    evidence_id=full_id,
                    source_name="ctrip",
                    confidence=0.6,
                    relevance_score=0.9,
                    place_name="五彩滩",
                )
            ],
            overall_confidence=0.6,
        ),
    )

    def bad_responder(system: str, user: str) -> str:
        return json.dumps(
            {
                "headline": "x",
                "conclusion": "关于五彩滩是否需要门票的问题，目前没有找到确切的官方",
                "sections": [],
                "limitations": [],
                "cited_evidence_ids": ["bogus-id"],
                "answer_text": "关于五彩滩是否需要门票的问题，目前没有找到确切的官方",
                "compose_mode": "fact_lookup",
            },
            ensure_ascii=False,
        )

    agent = AnswerComposerAgent(StubLLMClient(bad_responder))
    draft = asyncio.run(
        agent.compose(state, {"compose_mode": "fact_lookup", "target_label": "五彩滩"})
    )
    assert "50元" in draft.answer_text
    assert full_id in draft.cited_evidence_ids
    assert "合成服务不可用" not in draft.answer_text
