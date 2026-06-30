"""search_mcp limit, filter trace, URL cleaning, and ticket multi-query objectives."""

from __future__ import annotations

from datetime import datetime

from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.claim_gap_fill_planner import gap_tools_for_claim, order_gap_tools
from app.orchestrator.lookup_query_objectives import build_lookup_query_objectives
from app.orchestrator.ticket_lookup_helpers import collect_ticket_search_hits
from app.orchestrator.ticket_price_query_ladder import tiers_present
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, LicenseScope, SourceType
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from tools.mcp.adapters.search_mcp_adapter import SearchMCPAdapter
from tools.official_source.url_normalizer import clean_search_hit_for_official_chain, is_readable_page_url


def _kanas_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="喀纳斯湖游船船票多少钱？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="阿勒泰", places=["喀纳斯湖"]),
        information_needs=["boat_ticket_price"],
        requires_exact_fact=True,
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.structured_result = {"fact_anchor": {"resolved_name": "喀纳斯"}}
    return state


def test_search_mcp_resolve_limit_defaults_to_five():
    assert SearchMCPAdapter.resolve_search_limit({}) == 5
    assert SearchMCPAdapter.resolve_search_limit({"limit": 3}) == 5
    assert SearchMCPAdapter.resolve_search_limit({"top_k": 8}) == 8
    assert SearchMCPAdapter.resolve_search_limit({"max_results": 10, "limit": 6}) == 10


def test_search_mcp_filter_trace_when_single_kept():
    adapter = SearchMCPAdapter()
    raw = [
        {"title": "17173游戏萌妹阳光高考", "snippet": "攻略", "url": "https://www.17173.com/x"},
        {"title": "其他景区 unrelated", "snippet": "其他景区", "url": "https://example.com"},
        {"title": "喀纳斯游船", "snippet": "喀纳斯景区游船票价", "url": "https://gov.cn/kanas"},
    ]
    evidence = adapter._hits_to_evidence(
        raw,
        query="喀纳斯 游船 船票",
        country="China",
        city="阿勒泰",
        place_name="喀纳斯",
        information_need="boat_ticket_price",
    )
    assert len(evidence) == 1
    meta = adapter.last_run_meta
    assert meta["raw_result_count"] == 3
    assert meta["kept_result_count"] == 1
    assert meta["filtered_result_count"] == 2
    assert "spam" in meta["filter_reason"] or "irrelevant" in meta["filter_reason"]


def test_search_mcp_ticket_summary_without_amount_is_related_mention():
    adapter = SearchMCPAdapter()
    evidence = adapter._hits_to_evidence(
        [
            {
                "title": "那拉提景区门票预订_同程旅行",
                "snippet": "评分4.0/5，49条点评，开放时间10:00-19:00，18:00停止入园。",
                "url": "https://www.ly.com/scenery/BookSceneryTicket_228816.html",
            }
        ],
        query="那拉提景区 门票价格",
        country="China",
        city="伊犁",
        place_name="那拉提景区",
        information_need="ticket_price",
    )
    assert evidence
    claim = evidence[0].claims[0]
    assert claim.claim_type == ClaimType.TICKET_RELATED_MENTIONS


def test_search_mcp_ticket_summary_with_amount_is_price_candidate():
    adapter = SearchMCPAdapter()
    evidence = adapter._hits_to_evidence(
        [
            {
                "title": "那拉提景区门票预订",
                "snippet": "那拉提景区成人票95元起，价格以页面为准。",
                "url": "https://example.com/ticket",
            }
        ],
        query="那拉提景区 门票价格",
        country="China",
        city="伊犁",
        place_name="那拉提景区",
        information_need="ticket_price",
    )
    assert evidence
    claim = evidence[0].claims[0]
    assert claim.claim_type == ClaimType.TICKET_PRICE_CANDIDATE


def test_search_mcp_rejects_homonym_ticket_result_from_other_city():
    adapter = SearchMCPAdapter()
    evidence = adapter._hits_to_evidence(
        [
            {
                "title": "栖霞牟氏庄园景点介绍_门票价格_烟台旅游景点_西安康辉旅行社官网",
                "snippet": "景点门票：45 元 山东省栖霞牟氏庄园南街6号",
                "url": "https://www.sogou.com/link?url=wrapper",
            }
        ],
        query="栖霞山 门票 票价 官网",
        country="China",
        city="南京",
        place_name="栖霞山",
        information_need="ticket_price",
    )

    assert evidence == []
    assert "irrelevant" in adapter.last_run_meta["filter_reason"]


def test_search_mcp_filters_low_value_ticket_travel_article():
    adapter = SearchMCPAdapter()
    evidence = adapter._hits_to_evidence(
        [
            {
                "title": "南京评价很高的旅游景区，门票210却少有人知 - 知乎",
                "snippet": "南京知名景点有夫子庙、中山陵、栖霞山、牛首山等，适合周末游玩。",
                "url": "https://zhuanlan.zhihu.com/p/123",
            }
        ],
        query="栖霞山 门票 票价 官网",
        country="China",
        city="南京",
        place_name="栖霞山",
        information_need="ticket_price",
    )

    assert evidence == []
    assert "low_value_ticket" in adapter.last_run_meta["filter_reason"]


def test_clean_search_hit_unwraps_redirect_wrapper():
    hit = {
        "url": "https://www.baidu.com/link?url=wrapper",
        "title": "喀纳斯门票",
        "snippet": "官方票价见 https://www.xinjiang.gov.cn/ticket",
    }
    cleaned = clean_search_hit_for_official_chain(hit)
    assert cleaned is not None
    assert cleaned["url"] == "https://www.xinjiang.gov.cn/ticket"


def test_collect_ticket_search_hits_applies_url_cleaning():
    ev = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://www.baidu.com/link?url=wrapper",
        country="China",
        retrieved_at=datetime.utcnow(),
        data_freshness=DataFreshness.RECENT,
        license_scope=LicenseScope.PUBLIC_PAGE,
        confidence=0.5,
        claims=[
            Claim(
                claim_type=ClaimType.TRAVEL_ADVICE,
                value="喀纳斯门票",
                raw_text="喀纳斯门票 官方 https://kanas.gov.cn/price",
            )
        ],
    )
    state = TravelAgentState(session_id="s", query_id="q2", raw_user_query="喀纳斯门票", evidence=[ev])
    hits = collect_ticket_search_hits(state)
    assert hits
    assert any("kanas.gov.cn" in str(h.get("url") or "") for h in hits)


def test_ticket_lookup_multi_query_objectives_not_raw_query_only():
    state = _kanas_state()
    objs = build_lookup_query_objectives(state, "boat_ticket_price", "web_reference", max_objectives=4)
    assert len(objs) >= 3
    queries = [o.search_query for o in objs if o.search_query]
    assert queries
    assert not all(q == state.raw_user_query for q in queries)
    assert any("游船" in q or "船票" in q for q in queries)


def test_gap_tools_for_ticket_includes_official_and_platform():
    tools = gap_tools_for_claim("entrance_ticket_price")
    names = set(tools)
    assert "official_source_discovery_mcp" in names
    assert "official_page_reader_mcp" in names
    assert "browser_mcp" in names
    assert "search_mcp" in names
    assert "fliggy_ticket_api_mcp" in names or "ctrip_ticket_signal_crawler_mcp" in names


def test_order_ticket_gap_merges_full_pool_when_only_search_passed():
    state = _kanas_state()
    ordered = order_gap_tools(state, ["search_mcp"], claim_type="boat_ticket_price")
    names = set(ordered)
    assert "search_mcp" in names
    assert "official_source_discovery_mcp" in names
    assert "official_page_reader_mcp" in names
    assert "browser_mcp" in names


def test_order_ticket_gap_respects_allowed_whitelist():
    state = _kanas_state()
    ordered = order_gap_tools(
        state,
        ["search_mcp"],
        claim_type="boat_ticket_price",
        allowed=frozenset({"search_mcp"}),
    )
    assert ordered == ["search_mcp"]


def test_search_hits_from_evidence_includes_keyword_search_results():
    ev = Evidence(
        source_name="open-webSearch",
        source_type=SourceType.WEB,
        source_url="https://www.gov.cn/kanas",
        country="China",
        retrieved_at=datetime.utcnow(),
        data_freshness=DataFreshness.RECENT,
        license_scope=LicenseScope.PUBLIC_PAGE,
        confidence=0.5,
        claims=[Claim(claim_type=ClaimType.TRAVEL_ADVICE, value="喀纳斯", raw_text="喀纳斯门票")],
    )
    state = TravelAgentState(session_id="s", query_id="q3", raw_user_query="喀纳斯门票", evidence=[ev])
    state.structured_result = {
        "keyword_search_results": [
            {"url": "https://www.baidu.com/link?url=x", "title": "t", "snippet": "see https://kanas.gov.cn/ticket"}
        ]
    }
    planner_hits = ClaimSearchPlanner.search_hits_from_evidence(state)
    direct_hits = collect_ticket_search_hits(state)
    assert planner_hits == direct_hits
    assert any("kanas.gov.cn" in str(h.get("url") or "") for h in planner_hits)


def test_readable_page_url_rejects_lbsyun_platform():
    assert not is_readable_page_url("https://lbsyun.baidu.com/index.php?title=open/poitags")
    assert is_readable_page_url("https://www.xinjiang.gov.cn/ticket")


def test_ticket_price_escalation_covers_five_tiers():
    state = _kanas_state()
    present = tiers_present(state, max_queries=16)
    assert "official" in present
    assert "ticket_platform" in present
    assert "scenic_alias" in present
    assert "ticket_office" in present
    assert "announcement" in present
