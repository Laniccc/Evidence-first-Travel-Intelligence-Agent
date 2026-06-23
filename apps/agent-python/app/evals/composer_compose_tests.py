"""Unit tests for S8 AnswerComposerAgent (LLM path, no static fallback)."""

import asyncio
import json

from app.agents.answer_composer_agent import AnswerComposerAgent
from app.agents.composer_agent import ComposerAgent
from app.evals.llm_test_helpers import StubLLMClient
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_brief import CuratedClaimRow, EvidenceBrief
from app.schemas.final_answer_draft import FinalAnswerDraft
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
    draft = asyncio.get_event_loop().run_until_complete(
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

    draft = asyncio.get_event_loop().run_until_complete(
        AnswerComposerAgent(NoLLM()).compose(state, {"target_label": "测试地"})
    )
    assert "合成服务不可用" in draft.answer_text
    assert "No search hits" not in draft.answer_text
