"""Unit tests for ticket/review providers (no live HTTP/subprocess)."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.ticket_info import TicketSnapshot
from app.schemas.user_query import TravelAgentState
from tools.crawlers.ctrip_crawler_tool import CtripReviewCrawlerTool
from tools.ticketing.evidence_normalizer import (
    normalize_review_crawler_payload,
    normalize_ticketlens_items,
)
from tools.ticketing.ticket_snapshot_store import TicketSnapshotStore


def _frame(**kwargs) -> SemanticFrame:
    defaults = {
        "raw_query": "test",
        "normalized_request": "test",
        "decision_type": DecisionType.FACT_LOOKUP,
        "information_needs": ["ticket_price"],
        "entities": SemanticEntities(country="China", city="阿勒泰", places=["可可托海景区"]),
    }
    defaults.update(kwargs)
    return SemanticFrame(**defaults)


def test_ticket_providers_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TICKETLENS_ENABLED", "false")
    monkeypatch.setenv("CTRIP_CRAWLER_ENABLED", "false")
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "false")
    monkeypatch.setenv("DIANPING_CRAWLER_ENABLED", "false")
    get_settings.cache_clear()

    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(
                claim_type="ticket_price",
                priority="required",
                preferred_tools=["search_mcp"],
                model_prior_allowed=False,
            )
        ]
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="可可托海票价")
    state.semantic_frame = _frame(information_needs=["ticket_price"])
    state.response_contract = contract
    wl = ToolWhitelistBuilder().build(state)
    allowed = set(wl.allowed_tool_names())

    for tool in (
        "ticketlens_experience_mcp",
        "ctrip_review_crawler_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "dianping_review_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
    ):
        assert tool not in allowed
        assert tool in wl.blocked_tools
        assert wl.reason_by_tool.get(tool) in {"disabled_by_config", "not_configured", "missing_api_key"}


def test_ticket_review_providers_disabled_by_default(monkeypatch):
    """Spec alias for test_ticket_providers_disabled_by_default."""
    test_ticket_providers_disabled_by_default(monkeypatch)


def test_review_signal_schema_fields():
    from app.schemas.review_signal import ReviewSignalClaim, TicketSignalClaim

    review = ReviewSignalClaim(
        place_name="南京博物院",
        provider="Dianping",
        captured_at="2026-01-01T00:00:00Z",
        star_distribution={"5": 12, "4": 8},
        commercialization_risk="low",
        family_friendly="yes",
    )
    assert review.star_distribution["5"] == 12
    assert review.commercialization_risk == "low"

    ticket_signal = TicketSignalClaim(
        place_name="可可托海景区",
        provider="Ctrip",
        captured_at="2026-01-01T00:00:00Z",
        ticket_price_candidate_text="¥128起",
        ticket_related_mentions=["门票需预约"],
    )
    assert ticket_signal.ticket_price_candidate_text == "¥128起"


def test_crawler_provider_not_configured_without_command():
    settings = Settings(
        ctrip_crawler_enabled=True,
        enable_review_crawler_providers=True,
        ctrip_crawler_command="",
        ctrip_websearch_signal_enabled=False,
        mcp_search_enabled=True,
    )
    tool = CtripReviewCrawlerTool(settings)
    assert tool.is_configured() is False


def test_crawler_provider_configured_with_websearch_only():
    from tools.ticketing.provider_config import ctrip_crawler_configured, dianping_crawler_configured

    settings = Settings(
        ctrip_crawler_enabled=True,
        enable_review_crawler_providers=True,
        ctrip_crawler_command="",
        ctrip_websearch_signal_enabled=True,
        mcp_search_enabled=True,
        dianping_crawler_enabled=True,
        enable_ticket_crawler_providers=True,
        dianping_crawler_command="",
        dianping_websearch_signal_enabled=True,
    )
    assert ctrip_crawler_configured(settings) is True
    assert dianping_crawler_configured(settings) is True
    assert CtripReviewCrawlerTool(settings).is_configured() is True


def test_platform_websearch_hit_to_item_extracts_price():
    from tools.ticketing.platform_websearch_signal_service import PlatformWebSearchSignalService

    item = PlatformWebSearchSignalService._hit_to_item(
        {
            "title": "西湖游船-携程旅行",
            "url": "https://you.ctrip.com/sight/hangzhou/西湖游船.html",
            "snippet": "成人票¥69起，需提前预约",
        },
        platform="ctrip",
        ticket_focus=True,
    )
    assert item is not None
    assert "69" in str(item.get("price_text"))


def test_ticket_focus_accepts_goupiao():
    from tools.ticketing.platform_websearch_signal_service import PlatformWebSearchSignalService

    item = PlatformWebSearchSignalService._hit_to_item(
        {
            "title": "泰山风景区旅游攻略",
            "url": "https://you.ctrip.com/sight/taian/泰山.html",
            "snippet": "泰山是中国五岳之首，登山需购票",
        },
        platform="ctrip",
        ticket_focus=True,
    )
    assert item is not None
    assert "购票" in str(item.get("ticket_related_mentions"))


def test_ticket_focus_keeps_ctrip_sight_url():
    from tools.ticketing.platform_websearch_signal_service import PlatformWebSearchSignalService

    item = PlatformWebSearchSignalService._hit_to_item(
        {
            "title": "泰山风景区",
            "url": "https://you.ctrip.com/sight/taian/taishan.html",
            "snippet": "泰山景区介绍",
        },
        platform="ctrip",
        ticket_focus=True,
    )
    assert item is not None
    assert item.get("ticket_related_mentions") == ["platform_poi_page"]
    assert item.get("confidence") == 0.48


@pytest.mark.asyncio
async def test_platform_websearch_engine_error_message():
    from unittest.mock import AsyncMock, MagicMock

    from tools.mcp.client_manager import MCPInvokeResult
    from tools.ticketing.platform_websearch_signal_service import PlatformWebSearchSignalService

    client = MagicMock()
    client.is_server_configured.return_value = True
    client.open_websearch_search = AsyncMock(
        return_value=MCPInvokeResult(
            ok=True,
            data={"results": [], "totalResults": 0},
            meta={
                "engines_tried": ["baidu"],
                "partial_failures": [
                    {"engine": "baidu", "code": "engine_error", "message": "status 302"}
                ],
                "partial_failure_messages": ["baidu: engine_error (status 302)"],
            },
        )
    )
    svc = PlatformWebSearchSignalService(client=client)
    items, err = await svc.fetch_signal_items("ctrip", "泰山", "泰安", ticket_focus=True)
    assert items == []
    assert err is not None
    assert "failed" in err.lower() or "engine" in err.lower()
    assert svc.last_run_meta.get("partial_failures")


def test_fliggy_top_api_tool_configured_with_app_credentials():
    from tools.crawlers.fliggy_crawler_tool import FliggyTicketSnapshotCrawlerTool
    from tools.ticketing.provider_config import fliggy_api_configured, fliggy_top_api_configured

    settings = Settings(
        fliggy_ticket_crawler_enabled=True,
        enable_ticket_crawler_providers=True,
        fliggy_top_api_enabled=True,
        fliggy_app_key="12129701",
        fliggy_app_secret="test-secret",
    )
    assert fliggy_top_api_configured(settings) is True
    assert fliggy_api_configured(settings) is True
    tool = FliggyTicketSnapshotCrawlerTool(settings)
    assert tool.is_configured() is True


def test_fliggy_top_api_configured_with_app_credentials():
    from tools.ticketing.provider_config import fliggy_top_api_configured

    settings = Settings(
        fliggy_ticket_crawler_enabled=True,
        enable_ticket_crawler_providers=True,
        fliggy_top_api_enabled=True,
        fliggy_app_key="12129701",
        fliggy_app_secret="test-secret",
    )
    assert fliggy_top_api_configured(settings) is True


def test_fliggy_open_api_sign_and_scenic_parse():
    from tools.ticketing.fliggy_open_api_client import (
        FliggyOpenApiClient,
        scenics_get_response_to_items,
    )

    settings = Settings(
        fliggy_app_key="123456",
        fliggy_app_secret="secret",
        fliggy_api_sign_method="md5",
    )
    client = FliggyOpenApiClient(settings)
    params = {
        "method": "taobao.alitrip.travel.baseinfo.scenics.get",
        "app_key": "123456",
        "timestamp": "2026-01-01 12:00:00",
        "format": "json",
        "v": "2.0",
        "sign_method": "md5",
        "scenic": "西湖",
        "city": "杭州",
    }
    sign = client._sign(params, "secret")
    assert len(sign) == 32
    assert sign == sign.upper()

    sample = {
        "alitrip_travel_baseinfo_scenics_get_response": {
            "scenic_list": {
                "scenic_info": [
                    {
                        "scenic_id": 1001,
                        "scenic_name": "西湖",
                        "ticket_products": {
                            "ticket_product": [
                                {"product_name": "成人票", "price": 0, "price_text": "免费"},
                            ]
                        },
                    }
                ]
            }
        }
    }
    items = scenics_get_response_to_items(sample, max_results=5)
    assert len(items) == 1
    assert items[0]["ticket_type"] == "成人票"
    assert items[0]["price_text"] == "免费"


def test_ticketlens_normalize_ticket_candidate():
    items = [
        {
            "price_text": "¥128起",
            "ticket_type": "成人票",
            "booking_channel": "TicketLens",
            "url": "https://example.com/ticket",
            "confidence": 0.7,
        }
    ]
    evidence = normalize_ticketlens_items(items, place_name="可可托海景区", city="阿勒泰")
    assert len(evidence) == 1
    types = {c.claim_type for c in evidence[0].claims}
    assert ClaimType.TICKET_PRICE_CANDIDATE in types
    assert ClaimType.BOOKING_CHANNEL in types
    assert evidence[0].source_type == SourceType.TICKET_PLATFORM


def test_review_crawler_normalize_review_signal():
    payload = {
        "items": [
            {
                "review_summary": "景色不错，周末人多排队久。",
                "positive_aspects": ["风景好"],
                "negative_aspects": ["排队"],
                "ticket_related_mentions": ["门票偏贵"],
            }
        ]
    }
    evidence = normalize_review_crawler_payload(
        "Ctrip", payload, place_name="南京博物院", city="南京"
    )
    assert evidence
    types = {c.claim_type for c in evidence[0].claims}
    assert ClaimType.REVIEW_SUMMARY in types
    assert ClaimType.TICKET_RELATED_MENTIONS in types


def test_ticket_snapshot_store_save_and_query_latest(tmp_path):
    store = TicketSnapshotStore(tmp_path / "snapshots.sqlite3")
    snap = TicketSnapshot(
        snapshot_id="s1",
        place_name="可可托海景区",
        provider="Fliggy",
        ticket_type="成人票",
        price=128.0,
        currency="CNY",
        price_text="¥128",
        captured_at="2026-01-01T00:00:00Z",
        raw_hash="abc",
    )
    store.save_snapshot(snap)
    latest = store.query_latest("可可托海景区", provider="Fliggy")
    assert latest is not None
    assert latest.price == 128.0


def test_ticket_price_candidate_is_partial_not_strong():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="ticket_price", priority="required", model_prior_allowed=False),
        ]
    )
    ev = Evidence(
        source_name="TicketLens",
        source_type=SourceType.TICKET_PLATFORM,
        country="China",
        place_name="景区",
        claims=[
            Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="¥128起", confidence=0.7),
        ],
    )
    report = EvidenceCoverageChecker().check(contract, [ev], [])
    item = report.items[0]
    assert item.coverage_quality == "partial"
    assert item.covered is False


def test_review_signal_does_not_cover_ticket_price():
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="ticket_price", priority="required", model_prior_allowed=False),
        ]
    )
    ev = Evidence(
        source_name="Ctrip Crawler",
        source_type=SourceType.REVIEW_PLATFORM,
        country="China",
        place_name="景区",
        claims=[
            Claim(claim_type=ClaimType.REVIEW_SUMMARY, value="好评很多", confidence=0.6),
            Claim(claim_type=ClaimType.TICKET_RELATED_MENTIONS, value="门票不贵", confidence=0.5),
        ],
    )
    report = EvidenceCoverageChecker().check(contract, [ev], [])
    item = report.items[0]
    assert item.covered is False


def test_policy_guard_blocks_unconfigured_crawler_tool(monkeypatch):
    monkeypatch.setenv("CTRIP_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("ENABLE_REVIEW_CRAWLER_PROVIDERS", "true")
    monkeypatch.setenv("CTRIP_CRAWLER_COMMAND", "")
    monkeypatch.setenv("CTRIP_WEBSEARCH_SIGNAL_ENABLED", "false")
    monkeypatch.setenv("MCP_SEARCH_ENABLED", "false")
    get_settings.cache_clear()

    guard = EvidencePolicyGuard()
    action = AgentAction(
        action_type=AgentActionType.CALL_TOOL,
        target="ctrip_review_crawler_mcp",
        arguments={"place_name": "景区"},
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="评论怎么样")
    with pytest.raises(ValueError, match="not_configured"):
        guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


@pytest.mark.asyncio
async def test_tool_trace_includes_provider_meta():
    from tools.registry import TravelToolRegistry

    class _StubCtripTool:
        last_run_meta = {
            "provider": "Ctrip",
            "configured": True,
            "crawler_command": "python ctrip.py",
            "crawler_workdir": "/tmp/ctrip",
            "snapshot_saved_count": 2,
            "output_parse_status": "ok",
        }

        async def run(self, **kwargs):
            return [
                Evidence(
                    source_name="Ctrip Crawler",
                    source_type=SourceType.REVIEW_PLATFORM,
                    country="China",
                    place_name=kwargs.get("place_name", "景区"),
                    claims=[
                        Claim(
                            claim_type=ClaimType.REVIEW_SUMMARY,
                            value="stub",
                            confidence=0.5,
                        )
                    ],
                )
            ]

    registry = TravelToolRegistry(tool_mode="real")
    registry.ctrip_review_crawler_mcp = _StubCtripTool()
    await registry.run_tool("ctrip_review_crawler_mcp", place_name="景区")
    trace = registry.traces[-1]
    assert trace.provider == "Ctrip"
    assert trace.configured is True
    assert trace.crawler_command == "python ctrip.py"
    assert trace.crawler_workdir == "/tmp/ctrip"
    assert trace.snapshot_saved_count == 2
    assert trace.output_parse_status == "ok"


def test_base_crawler_parse_output_non_json():
    from tools.crawlers.base_crawler_tool import BaseCrawlerTool

    tool = BaseCrawlerTool()
    data, status = tool.parse_output("not json at all")
    assert status == "non_json"
    assert data is not None
    assert "items" in data
