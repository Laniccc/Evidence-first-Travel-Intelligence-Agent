"""Regression tests for elevation fact-lookup pipeline fixes."""

from app.orchestrator.evidence_brief_builder import build_evidence_brief_from_report
from app.orchestrator.evidence_evaluator import evaluate_evidence
from app.orchestrator.state_machine import TravelAgentStateMachine
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_brief import CuratedClaimRow
from app.schemas.evidence_decision_report import ClaimDecision, EvidenceDecisionReport
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.search_task import SearchTask, normalize_tool_parameters
from app.schemas.semantic_frame import SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def test_search_task_coerces_list_tool_parameters():
    task = SearchTask.model_validate(
        {
            "task_id": "t1",
            "search_query": "四姑娘山 海拔",
            "tool_parameters": {
                "additional_search_queries": ["四姑娘山景区 海拔", "四川四姑娘山 海拔"],
            },
        }
    )
    assert "additional_search_queries" in task.tool_parameters
    assert "四姑娘山景区 海拔" in task.tool_parameters["additional_search_queries"]
    assert "四川四姑娘山 海拔" in task.tool_parameters["additional_search_queries"]


def test_normalize_tool_parameters_joins_list():
    out = normalize_tool_parameters(
        {"additional_search_queries": ["a", "b"], "region": "四川"}
    )
    assert out["additional_search_queries"] == "a | b"
    assert out["region"] == "四川"


def test_search_mcp_maps_elevation_snippet_to_elevation_claim():
    from tools.mcp.adapters.search_mcp_adapter import SearchMCPAdapter

    adapter = SearchMCPAdapter()
    evidence = adapter._hits_to_evidence(
        {
            "results": [
                {
                    "title": "四姑娘山_百度百科",
                    "url": "https://baike.baidu.com/item/四姑娘山",
                    "snippet": "四姑娘山海拔6250米，位于四川省阿坝州小金县",
                }
            ],
            "totalResults": 1,
        },
        query="四姑娘山 海拔",
        country="China",
        city=None,
        place_name="四姑娘山",
        information_need="elevation",
    )
    assert evidence
    assert evidence[0].claims[0].claim_type == ClaimType.ELEVATION
    assert "6250" in str(evidence[0].claims[0].value)


def test_s7_elevation_web_evidence_gets_candidate_only():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="四姑娘山海拔多少",
        semantic_frame=SemanticFrame(
            raw_query="四姑娘山海拔多少",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", places=["四姑娘山"], region="四川"),
            information_needs=["elevation"],
            requires_exact_fact=True,
        ),
        response_contract=ResponseContract(
            claim_requirements=[
                ClaimRequirement(
                    claim_type="elevation",
                    priority="required",
                    missing_behavior="answer_with_limitation",
                )
            ]
        ),
        evidence=[
            Evidence(
                evidence_id="ev-1",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="四姑娘山",
                confidence=0.5,
                claims=[
                    Claim(
                        claim_type=ClaimType.ELEVATION,
                        value="四姑娘山海拔6250米",
                        confidence=0.5,
                    )
                ],
            ),
            Evidence(
                evidence_id="ev-2",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="四姑娘山",
                confidence=0.5,
                claims=[
                    Claim(
                        claim_type=ClaimType.ELEVATION,
                        value="主峰海拔约5355米",
                        confidence=0.48,
                    )
                ],
            ),
        ],
    )
    report = evaluate_evidence(state, target_label="四姑娘山")
    elevation = next(d for d in report.claim_decisions if d.claim_type == "elevation")
    assert elevation.adoption in {"candidate_only", "adopt_with_limitation"}
    assert elevation.adopted_evidence_ids


def test_evidence_brief_keeps_filter_rows_when_refuse_to_guess():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="四姑娘山海拔",
        evidence=[
            Evidence(
                evidence_id="ev-1",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="四姑娘山",
                confidence=0.5,
                claims=[
                    Claim(
                        claim_type=ClaimType.ELEVATION,
                        value="海拔6250米",
                        confidence=0.5,
                    )
                ],
            )
        ],
        structured_result={
            "curated_claims": [
                CuratedClaimRow(
                    claim_type="elevation",
                    value="海拔6250米",
                    evidence_id="ev-1",
                    source_name="open-webSearch",
                    confidence=0.5,
                    relevance_score=0.85,
                ).model_dump()
            ]
        },
    )
    report = EvidenceDecisionReport(
        claim_decisions=[
            ClaimDecision(
                claim_type="elevation",
                adoption="refuse_to_guess",
                coverage_quality="weak",
                confidence=0.3,
                adopted_evidence_ids=[],
            )
        ]
    )
    brief = build_evidence_brief_from_report(state, report, "四姑娘山")
    assert brief.curated_claims
    assert "6250" in brief.curated_claims[0].value


def test_evidence_preferred_skips_advisory_when_fact_pipeline_answered():
    state = TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="四姑娘山海拔多少",
        final_response="四姑娘山主峰海拔约6250米（候选线索，未官方核实）",
        semantic_frame=SemanticFrame(
            raw_query="四姑娘山海拔多少",
            task_family=TaskFamily.FACT_LOOKUP,
            entities=SemanticEntities(country="China", places=["四姑娘山"]),
            information_needs=["elevation"],
        ),
        evidence=[
            Evidence(
                evidence_id="ev-1",
                source_name="open-webSearch",
                source_type=SourceType.WEB,
                country="China",
                place_name="四姑娘山",
                confidence=0.5,
                claims=[Claim(claim_type=ClaimType.ELEVATION, value="6250米", confidence=0.5)],
            )
        ],
    )

    class _Resp:
        answer = state.final_response
        evidence_summary = [{"evidence_id": "ev-1"}]
        confidence = 0.2
        structured_result = None

    assert TravelAgentStateMachine._evidence_preferred_response_sufficient(state, _Resp())
