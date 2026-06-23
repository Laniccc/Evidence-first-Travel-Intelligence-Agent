"""S7 evidence evaluation and gap loop unit tests (no LLM / no external IO)."""

from app.agents.answer_composer_agent import AnswerComposerAgent
from app.orchestrator.claim_policy_registry import resolve_policy
from app.orchestrator.evidence_evaluator import evaluate_evidence
from app.orchestrator.evidence_gap_planner import EvidenceGapPlanner
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_gap_request import EvidenceGapLoopState, EvidenceGapRequest
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _review_evidence(place: str = "测试景点") -> Evidence:
    return Evidence(
        evidence_id="ev-review-1",
        source_name="Dianping Crawler",
        source_type=SourceType.REVIEW_PLATFORM,
        country="China",
        place_name=place,
        confidence=0.55,
        claims=[
            Claim(
                claim_type=ClaimType.REVIEW_SUMMARY,
                value="商业化一般，游客评价尚可",
                confidence=0.55,
            )
        ],
    )


def test_source_type_key_uses_valid_source_type_enums():
    from app.orchestrator.claim_policy_registry import source_type_key
    from app.schemas.evidence import SourceType

    assert source_type_key(SourceType.WEATHER_API, "weather") == "weather_api"
    assert source_type_key(SourceType.TRANSIT_API, "transit") == "map"
    assert source_type_key(SourceType.UNKNOWN, "open-webSearch") == "search_result"
    assert source_type_key("fallback", "tool") == "fallback"


    claim = ClaimRequirement(
        claim_type="photo_costume_suitability",
        claim_family="suitability_advice",
        claim_description="汉服拍照是否方便",
        priority="important",
    )
    policy = resolve_policy(claim)
    assert policy.policy_tier in {"family", "generic"}
    assert policy.claim_family == "suitability_advice"


def test_s7_generates_gap_request_for_unknown_claim_with_no_evidence():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="五彩滩适合穿汉服拍照吗",
        semantic_frame=SemanticFrame(
            raw_query="五彩滩适合穿汉服拍照吗",
            normalized_request="五彩滩适合穿汉服拍照吗",
            task_family=TaskFamily.SUITABILITY,
            entities=SemanticEntities(country="China", places=["五彩滩"]),
        ),
        response_contract=ResponseContract(
            claim_requirements=[
                ClaimRequirement(
                    claim_type="photo_costume_suitability",
                    claim_family="suitability_advice",
                    claim_description="汉服拍照是否方便",
                    priority="important",
                )
            ]
        ),
        gap_loop_state=EvidenceGapLoopState(max_gap_rounds=1),
    )
    report = evaluate_evidence(state, target_label="五彩滩")
    assert report.claim_decisions
    assert report.evidence_gap_requests
    assert report.evidence_gap_requests[0].claim_type == "photo_costume_suitability"


def test_s7_does_not_generate_gap_when_unknown_claim_has_relevant_review_evidence():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="五彩滩商业化严重吗",
        semantic_frame=SemanticFrame(
            raw_query="五彩滩商业化严重吗",
            normalized_request="五彩滩商业化严重吗",
            task_family=TaskFamily.SUITABILITY,
            entities=SemanticEntities(country="China", places=["五彩滩"]),
        ),
        response_contract=ResponseContract(
            claim_requirements=[
                ClaimRequirement(
                    claim_type="commercialization_risk",
                    claim_family="review_experience",
                    claim_description="商业化程度",
                    priority="important",
                )
            ]
        ),
        evidence=[_review_evidence("五彩滩")],
        gap_loop_state=EvidenceGapLoopState(max_gap_rounds=1),
    )
    report = evaluate_evidence(state, target_label="五彩滩")
    decision = report.claim_decisions[0]
    assert decision.coverage_quality in {"weak", "partial", "strong"}
    assert decision.adoption in {"adopt_with_limitation", "adopt", "candidate_only"}
    assert not report.evidence_gap_requests


def test_ticket_price_review_signal_not_adopted():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="五彩滩门票多少钱",
        response_contract=ResponseContract(
            claim_requirements=[
                ClaimRequirement(
                    claim_type="ticket_price",
                    claim_family="ticket_booking",
                    priority="required",
                    requires_exact_fact=True,
                    preferred_tools=["search_mcp"],
                )
            ]
        ),
        evidence=[
            Evidence(
                evidence_id="ev-dp",
                source_name="Dianping Crawler",
                source_type=SourceType.REVIEW_PLATFORM,
                country="China",
                place_name="五彩滩",
                confidence=0.5,
                claims=[
                    Claim(
                        claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                        value="¥96",
                        confidence=0.45,
                    )
                ],
            )
        ],
        gap_loop_state=EvidenceGapLoopState(max_gap_rounds=1),
    )
    report = evaluate_evidence(state, target_label="五彩滩")
    decision = report.claim_decisions[0]
    assert decision.coverage_quality != "strong"
    assert decision.adoption == "candidate_only"


def test_gap_loop_max_once():
    from app.orchestrator.state_machine import TravelAgentStateMachine

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    state.gap_loop_state = EvidenceGapLoopState(gap_round=1, max_gap_rounds=1)
    gap = EvidenceGapRequest(claim_type="ticket_price", suggested_tools=["search_mcp"])
    gap.ensure_signature()
    state.gap_loop_state.gap_signatures.append(gap.gap_signature)
    sm = TravelAgentStateMachine()
    assert sm._should_run_gap_fill(state) is False


def test_s5_gap_filling_uses_gap_suggested_tools():
    gap = EvidenceGapRequest(
        claim_type="ticket_price",
        suggested_tools=["search_mcp", "ctrip_ticket_signal_crawler_mcp"],
        forbidden_tools=["knowledge_prior"],
    )
    wl = ToolWhitelistBuilder().build_gap_whitelist(gap)
    names = wl.allowed_tool_names()
    assert "search_mcp" in names
    assert "knowledge_prior" not in names


def test_composer_respects_claim_decision_candidate_only():
    from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport

    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="门票",
        evidence_decision_report=EvidenceDecisionReport(
            claim_decisions=[
                ClaimDecision(
                    claim_type="ticket_price",
                    adoption="candidate_only",
                    coverage_quality="partial",
                    confidence=0.4,
                    reason="platform candidate only",
                )
            ]
        ),
    )
    rules = AnswerComposerAgent()._composition_rules(state, 0.4, None)
    assert any("候选信息" in r for r in rules)
    assert any("ticket_price" in r for r in rules)
