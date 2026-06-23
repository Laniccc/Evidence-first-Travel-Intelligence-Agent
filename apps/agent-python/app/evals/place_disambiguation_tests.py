"""Place disambiguation and S5 LLM-driven search strategy tests."""

from app.orchestrator.claim_policy_registry import resolve_policy
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.composition_preflight import (
    clear_premature_clarification_for_composition,
    should_compose_over_clarification,
)
from app.orchestrator.place_disambiguation_guard import (
    build_clarification_question,
    candidate_display_label,
    extract_place_candidates,
)
from app.agents.keyword_search_agent import KeywordSearchAgent
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport
from app.schemas.evidence_brief import CuratedClaimRow, EvidenceBrief
from app.schemas.search_task import SearchTask
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.tool_whitelist import ToolDescriptor, ToolWhitelist
from app.schemas.user_query import TravelAgentState


def _place_candidates_evidence() -> Evidence:
    return Evidence(
        evidence_id="ev-places",
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        place_name="五彩滩",
        confidence=0.6,
        claims=[
            Claim(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value=[
                    {"name": "阿勒泰地区"},
                    {"name": "北海市"},
                ],
                normalized_value={
                    "candidates": [
                        {"name": "阿勒泰地区"},
                        {"name": "北海市"},
                    ]
                },
            )
        ],
    )


def test_candidate_display_label_uses_name_when_region_missing():
    assert candidate_display_label({"name": "阿勒泰地区"}) == "阿勒泰地区"
    assert "新疆" in candidate_display_label({"province": "新疆", "city": "布尔津", "name": "五彩滩"})


def test_build_clarification_question_shows_candidate_names():
    text = build_clarification_question(
        "五彩滩",
        [{"name": "北海市"}, {"name": "阿勒泰地区"}],
    )
    assert "北海市" in text
    assert "阿勒泰地区" in text
    assert "未知省份" not in text


def test_planning_context_includes_place_candidates_for_llm():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="五彩滩门票",
        semantic_frame=SemanticFrame(
            raw_query="五彩滩门票",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", places=["五彩滩"]),
            information_needs=["ticket_price"],
        ),
        evidence=[_place_candidates_evidence()],
        structured_result={
            "completed_search_task_ids": ["t1", "t2"],
            "keyword_search_results": [
                {"task_id": "t1", "search_query": "五彩滩 门票", "evidence_count": 0},
            ],
        },
    )
    ctx = ClaimSearchPlanner.planning_context(state)
    assert len(ctx["place_candidates"]) == 2
    assert "五彩滩" in ctx["anchor_keywords"]
    assert ctx["keyword_search_count"] == 2
    assert ctx["recent_keyword_search_results"]


def test_keyword_search_agent_picks_tool_by_search_purpose():
    task = SearchTask(
        task_id="t1",
        anchor_keywords=["五彩滩"],
        search_query="五彩滩 阿勒泰 门票",
        information_need="ticket_price",
        preferred_tool="search_mcp",
    )
    wl = ToolWhitelist(
        state_name="evidence_planning_and_tool_use",
        allowed_tools=[
            ToolDescriptor(name="search_mcp", description="web search"),
            ToolDescriptor(name="ctrip_ticket_signal_crawler_mcp", description="ctrip"),
        ],
    )
    picked = KeywordSearchAgent.pick_tool(task, wl)
    assert picked in {"search_mcp", "ctrip_ticket_signal_crawler_mcp"}


def test_s8_clears_premature_clarification_when_candidate_only():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="五彩滩门票",
        final_response="五彩滩有多个同名地点？",
        next_state="clarification_response",
        limitations=["place_disambiguation"],
        evidence_decision_report=EvidenceDecisionReport(
            claim_decisions=[
                ClaimDecision(
                    claim_type="ticket_price",
                    adoption="candidate_only",
                    coverage_quality="partial",
                    confidence=0.4,
                )
            ]
        ),
        evidence_brief=EvidenceBrief(
            target_label="五彩滩",
            curated_claims=[
                CuratedClaimRow(
                    claim_type="ticket_price",
                    value="45元",
                    evidence_id="e1",
                    source_name="点评",
                    confidence=0.4,
                    relevance_score=0.4,
                )
            ],
        ),
    )
    assert should_compose_over_clarification(state)
    assert clear_premature_clarification_for_composition(state)
    assert state.final_response == ""


def test_unknown_claim_uses_generic_policy():
    claim = __import__(
        "app.schemas.response_contract", fromlist=["ClaimRequirement"]
    ).ClaimRequirement(
        claim_type="photo_costume_suitability",
        claim_family="suitability_advice",
        claim_description="汉服拍照是否方便",
        priority="important",
    )
    policy = resolve_policy(claim)
    assert policy.policy_tier in {"family", "generic"}
