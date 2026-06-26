"""Regression tests for Fliggy ticket API registration and ticket_price lookup chain."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings
from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.evidence_gap_planner import EvidenceGapPlanner
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.s5_domain_planner import S5DomainPlanner
from app.orchestrator.ticket_lookup_helpers import (
    collect_ticket_search_urls,
    is_ticket_price_noise_evidence,
)
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.response_contract import ClaimRequirement, ResponseContract
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.s5_information_domain import InformationDomain
from app.schemas.tool_trace import ToolTrace
from app.schemas.user_query import TravelAgentState
from tools.mcp.tool_specs import POLICY_TO_REGISTRY_ATTR
from tools.official_source.official_source_discovery_tool import OfficialSourceDiscoveryTool
from tools.ticketing.provider_config import (
    TICKET_PROVIDER_TOOL_NAMES,
    fliggy_api_block_reason,
    provider_configured_for_tool,
)


def _terracotta_ticket_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="兵马俑门票多少钱？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="西安", places=["秦始皇兵马俑博物馆"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=["ticket_price"],
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return state


def test_fliggy_registered_as_ticket_platform_provider():
    assert "fliggy_ticket_api_mcp" in TICKET_PROVIDER_TOOL_NAMES
    assert POLICY_TO_REGISTRY_ATTR["fliggy_ticket_api_mcp"] == "fliggy_ticket_api_mcp"


def test_ticket_booking_domain_includes_fliggy_when_configured(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    get_settings.cache_clear()

    state = _terracotta_ticket_state()
    plan = S5DomainPlanner().plan(
        state.response_contract,
        state.semantic_frame,
        intent_profile=state.intent_profile,
    )
    tools = {b.tool_name for b in plan.tool_bindings}
    assert InformationDomain.TICKET_BOOKING in plan.domains
    assert "fliggy_ticket_api_mcp" in tools
    assert "official_source_discovery_mcp" in tools
    wl = ToolWhitelistBuilder().build(state)
    assert "fliggy_ticket_api_mcp" in wl.allowed_tool_names()


def test_fliggy_visible_in_blocked_tools_when_disabled(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_API_ENABLED", "false")
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "false")
    get_settings.cache_clear()

    state = _terracotta_ticket_state()
    wl = ToolWhitelistBuilder().build(state)
    assert "fliggy_ticket_api_mcp" in wl.blocked_tools
    assert wl.reason_by_tool.get("fliggy_ticket_api_mcp") == "disabled_by_config"


def test_fliggy_missing_config_when_enabled_without_key(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "")
    monkeypatch.setenv("FLIGGY_TOP_API_ENABLED", "false")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert fliggy_api_block_reason(settings) == "missing_config"


def test_fliggy_flyai_configured_with_user_env(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    get_settings.cache_clear()
    from tools.ticketing.provider_config import fliggy_flyai_configured

    assert fliggy_flyai_configured(get_settings())


def test_ticket_gap_includes_fliggy_candidate_tool():
    state = _terracotta_ticket_state()
    claim = next(c for c in state.response_contract.claim_requirements if c.claim_type == "ticket_price")
    from app.orchestrator.claim_policy_registry import resolve_policy

    policy = resolve_policy(claim)
    decision = ClaimDecision(
        claim_type="ticket_price",
        adoption="omit",
        coverage_quality="none",
        reason="missing ticket price",
    )
    gap = EvidenceGapPlanner().plan_gaps(state, claim, policy, decision, gap_round=0, max_gap_rounds=2)
    assert gap is not None
    assert "fliggy_ticket_api_mcp" in gap.suggested_tools
    assert "ticketlens_experience_mcp" in gap.suggested_tools
    assert "official_page_reader_mcp" in gap.suggested_tools


def test_fliggy_ticket_candidate_to_ticket_price_partial():
    evidence = [
        Evidence(
            evidence_id="ev-fliggy",
            source_name="Fliggy",
            source_type=SourceType.TICKET_PLATFORM,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value="成人票 120 元",
                    confidence=0.65,
                )
            ],
            confidence=0.65,
        )
    ]
    contract = ResponseContract(
        claim_requirements=[
            ClaimRequirement(claim_type="ticket_price", priority="required", model_prior_allowed=False)
        ]
    )
    report = EvidenceCoverageChecker().check(contract, evidence, [])
    item = next(i for i in report.items if i.claim_type == "ticket_price")
    assert item.coverage_quality == "partial"
    assert not item.covered


def test_ticket_lookup_does_not_silently_drop_configured_platform_provider(monkeypatch):
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    get_settings.cache_clear()
    settings = get_settings()
    assert provider_configured_for_tool("fliggy_ticket_api_mcp", settings)


def test_ticket_lookup_rejects_unrelated_gov_homepage():
    ev = Evidence(
        evidence_id="ev-gov",
        source_name="gov",
        source_type=SourceType.WEB,
        country="China",
        source_url="https://www.shaanxi.gov.cn/",
        claims=[
            Claim(
                claim_type=ClaimType.GENERAL_FACT,
                value="陕西省人民政府门户网站首页",
                confidence=0.4,
            )
        ],
        confidence=0.4,
    )
    assert is_ticket_price_noise_evidence(ev)


@pytest.mark.asyncio
async def test_official_discovery_receives_search_urls():
    tool = OfficialSourceDiscoveryTool()
    evidence = await tool.run(
        place_name="秦始皇兵马俑博物馆",
        country="China",
        city="西安",
        claim_type="ticket_price",
        urls=["https://www.bmy.com.cn/"],
        search_results=[{"url": "https://www.bmy.com.cn/index.html", "title": "秦始皇帝陵博物院"}],
    )
    assert tool.last_run_meta.get("urls_checked_count", 0) >= 1
    assert evidence


def test_collect_ticket_search_urls_from_evidence():
    state = _terracotta_ticket_state()
    state.evidence = [
        Evidence(
            evidence_id="ev-search",
            source_name="open-websearch",
            source_type=SourceType.WEB,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.GENERAL_FACT,
                    value="官网 https://www.bmy.com.cn/index.html 门票信息",
                    confidence=0.5,
                )
            ],
            confidence=0.5,
        )
    ]
    urls = collect_ticket_search_urls(state)
    assert any("bmy.com.cn" in u for u in urls)


def _qixia_ticket_state() -> TravelAgentState:
    frame = SemanticFrame(
        raw_query="栖霞山门票多少钱？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="南京", places=["栖霞山"]),
        information_needs=["ticket_price"],
        requires_exact_fact=True,
    )
    profile = IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        intent_subtypes=["ticket_price"],
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = profile
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    state.structured_result = {
        "fact_anchor": {
            "resolved_name": "南京栖霞山风景名胜区",
            "canonical_name": "南京栖霞山风景名胜区",
            "confidence": 0.9,
        }
    }
    return state


def _ticket_retrieval_attempted_state(monkeypatch) -> TravelAgentState:
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    get_settings.cache_clear()
    state = _qixia_ticket_state()
    state.tool_traces = [
        ToolTrace(tool_name="search_mcp"),
        ToolTrace(tool_name="official_source_discovery_mcp"),
        ToolTrace(tool_name="official_page_reader_mcp"),
        ToolTrace(tool_name="fliggy_ticket_api_mcp"),
    ]
    return state


def test_ticket_lookup_finish_with_gap_ack_not_max_steps(monkeypatch):
    from app.orchestrator.actions import AgentAction, AgentActionType
    from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
    from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
    from app.orchestrator.ticket_lookup_policy import ticket_lookup_retrieval_complete

    state = _ticket_retrieval_attempted_state(monkeypatch)
    assert ticket_lookup_retrieval_complete(state)
    guard = EvidencePolicyGuard()
    action = AgentAction(action_type=AgentActionType.FINISH_STATE, arguments={})
    guard.validate(action, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, state)


def test_fliggy_called_only_in_platform_ticket_phase():
    from app.orchestrator.lookup_research_chain import save_lookup_chain
    from app.orchestrator.ticket_lookup_policy import ticket_platform_tool_allowed
    from app.schemas.lookup_research_chain import LookupResearchChainState

    state = _qixia_ticket_state()
    save_lookup_chain(state, LookupResearchChainState(current_phase="entity_anchor"))
    assert not ticket_platform_tool_allowed(state, "fliggy_ticket_api_mcp")
    save_lookup_chain(state, LookupResearchChainState(current_phase="platform_ticket_candidate"))
    assert ticket_platform_tool_allowed(state, "fliggy_ticket_api_mcp")


def test_fliggy_mcp_args_force_ticket_price_claim():
    from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments

    state = _qixia_ticket_state()
    args = enrich_mcp_tool_arguments(
        "fliggy_ticket_api_mcp",
        {"information_need": "entity_resolution", "claim_type": "entity_resolution"},
        state=state,
    )
    assert args["information_need"] == "ticket_price"
    assert args["claim_type"] == "ticket_price"
    assert "栖霞山博物馆" not in (args.get("aliases") or [])
    assert "栖霞山博物院" not in (args.get("aliases") or [])


def test_ticket_alias_generator_no_fake_museum_alias_for_mountain():
    from app.orchestrator.ticket_lookup_helpers import build_ticket_place_aliases

    state = _qixia_ticket_state()
    aliases = build_ticket_place_aliases(state)
    assert any("栖霞山" in a for a in aliases)
    assert not any("博物馆" in a or "博物院" in a for a in aliases)


def test_ticket_gap_tools_include_platform_and_official_reader(monkeypatch):
    from app.schemas.evidence_gap_request import EvidenceGapRequest

    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    get_settings.cache_clear()

    gap = EvidenceGapRequest(
        claim_type="ticket_price",
        claim_family="ticket_booking",
        claim_description="门票价格",
        reason="missing ticket price",
        suggested_tools=[
            "official_source_discovery_mcp",
            "official_page_reader_mcp",
            "search_mcp",
            "fliggy_ticket_api_mcp",
        ],
    )
    wl = ToolWhitelistBuilder().build_gap_whitelist(gap)
    allowed = set(wl.allowed_tool_names())
    assert "search_mcp" in allowed
    assert "official_page_reader_mcp" in allowed or "official_page_reader_mcp" in wl.blocked_tools
    assert "fliggy_ticket_api_mcp" in allowed
    assert len(allowed) >= 3


def test_official_background_page_does_not_cover_ticket_price():
    from app.orchestrator.fact_lookup_policy import collect_fact_clues
    from app.orchestrator.ticket_lookup_helpers import is_official_background_only_for_ticket
    from app.schemas.official_source import SOURCE_CLASS_OFFICIAL_GOVERNMENT

    cand = {
        "url": "https://www.njqixia.gov.cn/",
        "domain": "njqixia.gov.cn",
        "title": "南京市栖霞区人民政府",
        "source_class": SOURCE_CLASS_OFFICIAL_GOVERNMENT,
        "official_confidence": 0.95,
        "supports_claim_types": ["destination_background"],
        "has_ticket_info": False,
    }
    ev = Evidence(
        evidence_id="ev-gov-bg",
        source_name="official_source_discovery",
        source_type=SourceType.OFFICIAL,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                value="南京市栖霞区人民政府",
                normalized_value=cand,
                confidence=0.95,
            )
        ],
        confidence=0.95,
    )
    assert is_official_background_only_for_ticket(ev)
    assert is_ticket_price_noise_evidence(ev)
    state = _qixia_ticket_state()
    state.evidence = [
        ev,
        Evidence(
            evidence_id="ev-price",
            source_name="search",
            source_type=SourceType.WEB,
            country="China",
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value="成人票 50 元",
                    confidence=0.5,
                )
            ],
            confidence=0.5,
        ),
    ]
    clues = collect_fact_clues(state)
    assert all("人民政府" not in (c.get("text") or "") for c in clues)


def test_s8_ticket_price_limitations_filter_irrelevant_weather_profile():
    from app.orchestrator.ticket_lookup_policy import filter_ticket_price_limitations

    raw = [
        "未提供出行日期，旺季票价可能变化。",
        "未提供出行日期，天气评估使用默认近日假设。",
        "未提供同行人画像，按一般游客评估。",
        "官方票价页未确认。",
    ]
    kept = filter_ticket_price_limitations(raw, need="ticket_price")
    assert any("官方票价" in x for x in kept)
    assert not any("天气" in x for x in kept)
    assert not any("同行人" in x for x in kept)
