"""SubagentEvidenceGate tests for NEARBY tasks."""

from __future__ import annotations

from app.orchestrator.subagent_evidence_gate import filter_subagent_evidence
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.semantic_frame import DecisionType, SemanticFrame
from app.schemas.user_query import TravelAgentState


def _nearby_state() -> TravelAgentState:
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="明故宫附近有什么好吃的？",
        semantic_frame=SemanticFrame(
            raw_query="明故宫附近有什么好吃的？",
            decision_type=DecisionType.NEARBY_SEARCH,
        ),
    )


def _lookup_state() -> TravelAgentState:
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query="故宫开放时间",
        semantic_frame=SemanticFrame(
            raw_query="故宫开放时间",
            decision_type=DecisionType.FACT_LOOKUP,
        ),
    )


def test_gate_noop_for_lookup_task():
    junk = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://gaokao.chsi.com.cn/foo",
        country="China",
        claims=[Claim(claim_type=ClaimType.TRAVEL_ADVICE, value="无关")],
    )
    accepted, rejected = filter_subagent_evidence(
        _lookup_state(),
        [junk],
        subagent="fact_search_agent",
        output={"claim_target": "opening_hours"},
    )
    assert len(accepted) == 1
    assert rejected == []


def test_gate_keeps_map_coordinates():
    ev = Evidence(
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        city="南京",
        claims=[
            Claim(
                claim_type=ClaimType.COORDINATES,
                value={"latitude": 32.04, "longitude": 118.81},
            )
        ],
    )
    accepted, rejected = filter_subagent_evidence(
        _nearby_state(),
        [ev],
        subagent="entity_resolution_agent",
        output={"claim_target": "entity_resolution"},
    )
    assert len(accepted) == 1
    assert rejected == []


def test_gate_drops_review_with_junk_url():
    junk = Evidence(
        source_name="Dianping Crawler",
        source_type=SourceType.REVIEW_PLATFORM,
        source_url="https://gaokao.chsi.com.cn/zsgs",
        country="China",
        claims=[Claim(claim_type=ClaimType.REVIEW_SUMMARY, value="招生信息")],
    )
    accepted, rejected = filter_subagent_evidence(
        _nearby_state(),
        [junk],
        subagent="fact_search_agent",
        output={"claim_target": "nearby_food", "information_need": "nearby_food"},
    )
    assert accepted == []
    assert rejected[0]["reason"] == "nearby_gate:junk_domain"


def test_gate_drops_review_platform_off_domain():
    junk = Evidence(
        source_name="Ctrip Crawler",
        source_type=SourceType.REVIEW_PLATFORM,
        source_url="https://www.vw.com.cn/promo",
        country="China",
        claims=[Claim(claim_type=ClaimType.REVIEW_SUMMARY, value="汽车促销")],
    )
    accepted, rejected = filter_subagent_evidence(
        _nearby_state(),
        [junk],
        subagent="fact_search_agent",
        output={"claim_target": "nearby_food"},
    )
    assert accepted == []
    assert rejected[0]["reason"] == "nearby_gate:junk_domain"


def test_gate_keeps_dianping_review_on_platform():
    ok = Evidence(
        source_name="Dianping Crawler",
        source_type=SourceType.REVIEW_PLATFORM,
        source_url="https://www.dianping.com/shop/12345",
        country="China",
        claims=[Claim(claim_type=ClaimType.REVIEW_SUMMARY, value="口味不错")],
    )
    accepted, rejected = filter_subagent_evidence(
        _nearby_state(),
        [ok],
        subagent="fact_search_agent",
        output={"claim_target": "nearby_food"},
    )
    assert len(accepted) == 1
    assert rejected == []


def test_gate_drops_search_mcp_travel_advice_only_for_nearby_food():
    junk = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://example.com/blog",
        country="China",
        claims=[Claim(claim_type=ClaimType.TRAVEL_ADVICE, value="南京旅游攻略")],
    )
    accepted, rejected = filter_subagent_evidence(
        _nearby_state(),
        [junk],
        subagent="fact_search_agent",
        output={"claim_target": "nearby_food"},
    )
    assert accepted == []
    assert rejected[0]["reason"] == "nearby_gate:search_mcp_travel_advice_only"


def test_gate_drops_baidu_map_travel_advice_only_for_nearby_food():
    junk = Evidence(
        source_name="Baidu Maps MCP",
        source_type=SourceType.MAP,
        country="China",
        claims=[Claim(claim_type=ClaimType.TRAVEL_ADVICE, value='{"status":0}')],
    )
    accepted, rejected = filter_subagent_evidence(
        _nearby_state(),
        [junk],
        subagent="fact_search_agent",
        output={"claim_target": "nearby_food"},
    )
    assert accepted == []
    assert rejected[0]["reason"] == "nearby_gate:map_travel_advice_only"
