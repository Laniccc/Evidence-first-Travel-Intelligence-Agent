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
    mark_disambiguation_pending,
    next_disambiguation_branch,
    record_disambiguation_branch_done,
)
from tools.mcp.adapters.baidu_response_parser import candidates_are_ambiguous
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


def test_candidates_are_ambiguous_detects_distinct_regions():
    assert candidates_are_ambiguous(
        [
            {"name": "云峰山", "province": "辽宁", "city": "丹东"},
            {"name": "云峰山", "province": "湖南", "city": "衡阳"},
        ]
    )
    assert not candidates_are_ambiguous([{"name": "可可托海", "city": "阿勒泰"}])


def test_disambiguation_branch_queue_advances_per_region():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="云峰山门票",
        semantic_frame=SemanticFrame(
            raw_query="云峰山门票",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", places=["云峰山"]),
            information_needs=["ticket_price"],
        ),
    )
    mark_disambiguation_pending(
        state,
        [
            {"name": "云峰山", "province": "辽宁", "city": "丹东"},
            {"name": "云峰山", "province": "湖南", "city": "衡阳"},
        ],
    )
    first = next_disambiguation_branch(state)
    assert first is not None
    assert first["region"] == "丹东"
    record_disambiguation_branch_done(state, first["_branch_key"])
    second = next_disambiguation_branch(state)
    assert second is not None
    assert second["region"] == "衡阳"


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
        lookup_intent="查询五彩滩门票价格",
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


def test_s8_does_not_clear_premature_clarification_when_place_disambiguation_needed():
    from app.orchestrator.place_disambiguation_composition import (
        should_present_place_disambiguation_at_s8,
    )

    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="白沙湖海拔多少",
        final_response="白沙湖有多个同名地点？",
        next_state="clarification_response",
        limitations=["place_disambiguation"],
        semantic_frame=SemanticFrame(
            raw_query="白沙湖海拔多少",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", places=["白沙湖"], region="新疆"),
            information_needs=["elevation"],
        ),
        evidence=[
            _place_candidates_evidence_extended(),
        ],
        structured_result={
            "place_disambiguation_pending": True,
            "place_disambiguation_candidates": [
                {"name": "白沙湖", "province": "新疆", "city": "喀什"},
                {"name": "白沙湖", "province": "云南", "city": "丽江"},
            ],
        },
        evidence_decision_report=EvidenceDecisionReport(
            claim_decisions=[
                ClaimDecision(
                    claim_type="elevation",
                    adoption="refuse_to_guess",
                    coverage_quality="weak",
                    confidence=0.3,
                    reason="多地同名，无法唯一采纳",
                )
            ]
        ),
    )
    assert should_present_place_disambiguation_at_s8(state)
    assert not should_compose_over_clarification(state)


def _place_candidates_evidence_extended() -> Evidence:
    return Evidence(
        evidence_id="ev-places",
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        place_name="白沙湖",
        confidence=0.6,
        claims=[
            Claim(
                claim_type=ClaimType.PLACE_CANDIDATES,
                value=[],
                normalized_value={
                    "candidates": [
                        {"name": "白沙湖", "province": "新疆", "city": "喀什"},
                        {"name": "白沙湖", "province": "云南", "city": "丽江"},
                    ]
                },
            )
        ],
    )


def test_s8_disambiguation_draft_lists_each_candidate_with_evidence():
    from app.orchestrator.place_disambiguation_composition import build_disambiguation_draft

    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="白沙湖海拔多少",
        semantic_frame=SemanticFrame(
            raw_query="白沙湖海拔多少",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", places=["白沙湖"]),
            information_needs=["elevation"],
        ),
        evidence=[
            _place_candidates_evidence_extended(),
            Evidence(
                evidence_id="ev-xj",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="白沙湖 新疆 喀什",
                confidence=0.6,
                claims=[
                    Claim(
                        claim_type=ClaimType.ELEVATION,
                        value="约3300米",
                        confidence=0.5,
                    )
                ],
            ),
            Evidence(
                evidence_id="ev-yn",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="白沙湖 云南",
                confidence=0.4,
                claims=[
                    Claim(
                        claim_type=ClaimType.ELEVATION,
                        value="约2400米",
                        confidence=0.4,
                    )
                ],
            ),
        ],
        structured_result={
            "place_disambiguation_pending": True,
            "place_disambiguation_candidates": [
                {"name": "白沙湖", "province": "新疆", "city": "喀什"},
                {"name": "白沙湖", "province": "云南", "city": "丽江"},
            ],
        },
        evidence_decision_report=EvidenceDecisionReport(
            claim_decisions=[
                ClaimDecision(
                    claim_type="elevation",
                    adoption="refuse_to_guess",
                    coverage_quality="weak",
                    confidence=0.3,
                )
            ]
        ),
    )
    draft = build_disambiguation_draft(state)
    text = draft.render_text()
    assert "多个同名地点" in text
    assert "新疆" in text
    assert "云南" in text or "丽江" in text
    assert "3300" in text or "2400" in text
    assert "回复序号" in text or "序号" in text
    assert draft.compose_mode == "place_disambiguation"
    assert len(draft.sections) >= 2


def test_resolve_compose_mode_place_disambiguation():
    from app.orchestrator.state_machine import TravelAgentStateMachine

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
    mode = TravelAgentStateMachine._resolve_compose_mode(state)
    assert mode != "place_disambiguation"


def _xuanwu_lake_candidates() -> list[dict]:
    return [
        {
            "name": "玄武湖景区",
            "province": "江苏省",
            "city": "南京市",
            "address": "南京市玄武区玄武巷1号",
            "latitude": 32.076613,
            "longitude": 118.805436,
        },
        {
            "name": "玄武湖景区-和平门",
            "province": "江苏省",
            "city": "南京市",
            "address": "南京市玄武区龙蟠路8号",
            "latitude": 32.082030,
            "longitude": 118.810703,
        },
        {
            "name": "玄武湖公园-解放门",
            "province": "江苏省",
            "city": "南京市",
            "address": "南京市玄武区玄武巷1号",
            "latitude": 32.089427,
            "longitude": 118.805884,
        },
    ]


def test_nearby_food_keeps_disambiguation_when_same_scenic_area():
    from app.orchestrator.place_disambiguation_composition import (
        should_present_place_disambiguation_at_s8,
    )

    candidates = _xuanwu_lake_candidates()
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="玄武湖北门附近有什么好吃的？",
        semantic_frame=SemanticFrame(
            raw_query="玄武湖北门附近有什么好吃的？",
            task_family=TaskFamily.ADVISORY,
            entities=SemanticEntities(country="China", city="南京", places=["玄武湖"]),
            information_needs=["nearby_food"],
        ),
        evidence=[
            Evidence(
                evidence_id="ev-places",
                source_name="Baidu Maps MCP",
                source_type=SourceType.MAP,
                country="China",
                city="南京市",
                place_name="玄武湖景区",
                claims=[
                    Claim(
                        claim_type=ClaimType.PLACE_CANDIDATES,
                        value=candidates,
                        normalized_value={"candidates": candidates},
                    )
                ],
            ),
            Evidence(
                evidence_id="ev-food",
                source_name="Baidu Maps MCP",
                source_type=SourceType.MAP,
                country="China",
                city="南京市",
                place_name="寻魏·金陵十二菜(玄武湖店)",
                claims=[
                    Claim(
                        claim_type=ClaimType.FOOD,
                        value="寻魏·金陵十二菜(玄武湖店)（南京市玄武区龙蟠路）",
                        normalized_value={
                            "name": "寻魏·金陵十二菜(玄武湖店)",
                            "address": "南京市玄武区龙蟠路",
                            "latitude": 32.0815,
                            "longitude": 118.812,
                            "information_need": "nearby_food",
                        },
                        confidence=0.68,
                    )
                ],
            ),
        ],
        evidence_decision_report=EvidenceDecisionReport(
            claim_decisions=[
                ClaimDecision(
                    claim_type="nearby_food",
                    adoption="adopt_with_limitation",
                    coverage_quality="weak",
                    confidence=0.45,
                    adopted_evidence_ids=["ev-food"],
                )
            ]
        ),
    )
    assert should_present_place_disambiguation_at_s8(state)


def test_nearby_food_disambiguation_assigns_restaurant_to_nearest_gate():
    from app.orchestrator.place_disambiguation_composition import build_disambiguation_draft

    candidates = _xuanwu_lake_candidates()
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="玄武湖北门附近有什么好吃的？",
        semantic_frame=SemanticFrame(
            raw_query="玄武湖北门附近有什么好吃的？",
            task_family=TaskFamily.ADVISORY,
            entities=SemanticEntities(country="China", city="南京", places=["玄武湖"]),
            information_needs=["nearby_food"],
        ),
        evidence=[
            Evidence(
                evidence_id="ev-places",
                source_name="Baidu Maps MCP",
                source_type=SourceType.MAP,
                country="China",
                city="南京市",
                place_name="玄武湖景区",
                claims=[
                    Claim(
                        claim_type=ClaimType.PLACE_CANDIDATES,
                        value=candidates,
                        normalized_value={"candidates": candidates},
                    )
                ],
            ),
            Evidence(
                evidence_id="ev-food",
                source_name="Baidu Maps MCP",
                source_type=SourceType.MAP,
                country="China",
                city="南京市",
                place_name="寻魏·金陵十二菜(玄武湖店)",
                claims=[
                    Claim(
                        claim_type=ClaimType.FOOD,
                        value="寻魏·金陵十二菜(玄武湖店)（南京市玄武区龙蟠路）",
                        normalized_value={
                            "name": "寻魏·金陵十二菜(玄武湖店)",
                            "address": "南京市玄武区龙蟠路",
                            "latitude": 32.0815,
                            "longitude": 118.812,
                            "information_need": "nearby_food",
                        },
                        confidence=0.68,
                    )
                ],
            ),
        ],
        evidence_decision_report=EvidenceDecisionReport(
            claim_decisions=[
                ClaimDecision(
                    claim_type="nearby_food",
                    adoption="refuse_to_guess",
                    coverage_quality="weak",
                    confidence=0.4,
                )
            ]
        ),
    )
    draft = build_disambiguation_draft(state)
    text = draft.render_text()
    assert "多个同名地点" in text or "请先确认" in text
    assert "寻魏" in text or "金陵十二菜" in text
    assert "和平门" in text
    assert draft.compose_mode == "place_disambiguation"


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
