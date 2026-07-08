"""Regression coverage for task-class matrix failures found in live runs."""

from __future__ import annotations

from app.orchestrator.intent_profile_deriver import IntentProfileDeriver
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.mcp_tool_arguments import enrich_mcp_tool_arguments
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.response_sanitizer import sanitize_answer_text, sanitize_limitations
from app.orchestrator.s5_diversified_tool_selector import S5DiversifiedToolSelector
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.schemas.intent_profile import PrimaryIntent
from app.schemas.semantic_frame import DecisionType, QueryScope, SemanticEntities, SemanticFrame, TaskFamily
from app.schemas.user_query import TravelAgentState


def _frame(query: str, *, needs: list[str] | None = None, places: list[str] | None = None) -> SemanticFrame:
    return SemanticFrame(
        raw_query=query,
        normalized_request=query,
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.FACT_LOOKUP,
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="北京", places=places or ["测试地点"]),
        information_needs=needs or [],
        requires_exact_fact=True,
    )


def _state(frame: SemanticFrame) -> TravelAgentState:
    profile = IntentProfileDeriver().derive(frame)
    contract = ResponseContractCompiler().compile(frame, intent_profile=profile)
    return TravelAgentState(
        session_id="s",
        query_id="q",
        raw_user_query=frame.raw_query,
        semantic_frame=frame,
        intent_profile=profile,
        intent_strategy=resolve_intent_strategy(profile),
        response_contract=contract,
    )


def test_elevation_query_suppresses_spurious_ticket_claim():
    query = "泰山海拔多少米？"
    frame = _frame(query, needs=["ticket_price"], places=["泰山"])
    state = _state(frame)

    assert state.intent_profile is not None
    assert state.intent_profile.primary_intent == PrimaryIntent.LOOKUP
    claim_types = [c.claim_type for c in state.response_contract.claim_requirements]

    assert "elevation" in claim_types
    assert "ticket_price" not in claim_types
    assert "entrance_ticket_price" not in claim_types
    assert S5DiversifiedToolSelector(state).sequence_key_for_claim("elevation") == "geo_fact_lookup"


def test_route_query_is_planning_and_enriches_origin_destination():
    query = "从北京南站到天安门广场坐地铁怎么走？"
    frame = SemanticFrame(
        raw_query=query,
        normalized_request=query,
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.UNKNOWN,
        decision_type=DecisionType.UNKNOWN,
        entities=SemanticEntities(country="China", city="北京", places=["天安门广场"]),
        information_needs=[],
    )
    state = _state(frame)

    assert state.intent_profile is not None
    assert state.intent_profile.primary_intent == PrimaryIntent.PLANNING
    assert S5DiversifiedToolSelector(state).sequence_key_for_claim("route_plan") == "route_first"

    args = enrich_mcp_tool_arguments("baidu_route_mcp", {}, state=state)
    assert args["origin"] == "北京南站"
    assert args["destination"] == "天安门广场"
    assert args["mode"] == "transit"


def test_review_query_is_review_first_not_live_status():
    query = "广州长隆野生动物世界排队久不久？"
    frame = SemanticFrame(
        raw_query=query,
        normalized_request=query,
        query_scope=QueryScope.PLACE,
        task_family=TaskFamily.UNKNOWN,
        decision_type=DecisionType.UNKNOWN,
        entities=SemanticEntities(country="China", city="广州", places=["广州长隆野生动物世界"]),
        information_needs=[],
    )
    state = _state(frame)

    assert state.intent_profile is not None
    assert state.intent_profile.primary_intent == PrimaryIntent.REVIEW_CHECK
    assert S5DiversifiedToolSelector(state).sequence_key_for_claim("review_summary") == "review_first"


def test_ticket_price_must_attempts_fliggy_early(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("ENABLE_TICKET_CRAWLER_PROVIDERS", "true")
    monkeypatch.setenv("FLIGGY_TICKET_CRAWLER_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_ENABLED", "true")
    monkeypatch.setenv("FLIGGY_FLYAI_API_KEY", "sk-test")
    get_settings.cache_clear()

    query = "栖霞山门票价格多少？"
    frame = _frame(query, needs=["ticket_price"], places=["栖霞山"])
    state = _state(frame)
    wl = ToolWhitelistBuilder().build(state, prompt_context={})
    plan = S5DiversifiedToolSelector(state).build_claim_plan("ticket_price", whitelist=wl)

    assert plan.sequence_key == "ticket_price_lookup"
    assert "fliggy_ticket_api_mcp" in plan.must_attempt
    assert plan.must_attempt.index("fliggy_ticket_api_mcp") <= 1
    get_settings.cache_clear()


def test_ticket_charge_policy_queries_include_free_open_area_angles():
    from app.orchestrator.ticket_price_query_ladder import build_ticket_price_escalation_queries

    frame = _frame("夫子庙需要收费吗", needs=["ticket_price"], places=["夫子庙"])
    state = _state(frame)
    queries = [q for _tier, q in build_ticket_price_escalation_queries(state)]

    assert any("免费开放" in q and "需要门票" in q for q in queries)
    assert any("内部景点" in q and "单独购票" in q for q in queries)


def test_response_sanitizer_hides_internal_diagnostics():
    limitations = sanitize_limitations(
        [
            "S5 gap-fill completed for ticket_price",
            "Missing source URL for Official Source Discovery",
            "未提供出行日期，天气评估使用默认近日假设。",
            "未接入实时人流/排队数据，拥挤判断基于评价摘要估算。",
            "未接入实时人流/排队数据，拥挤判断基于评价摘要估算。",
        ]
    )
    assert limitations == ["未接入实时人流/排队数据，拥挤判断基于评价摘要估算。"]

    answer = sanitize_answer_text(
        "结论：可以参考平台候选价。\n"
        "- S5 gap-fill completed for ticket_price\n"
        "- Missing source URL for Official Source Discovery\n"
        "- 官方票价未确认。"
    )
    assert "S5 gap-fill" not in answer
    assert "Missing source URL" not in answer
    assert "官方票价未确认" in answer


def test_ticket_fact_composition_uses_deterministic_template_only_for_pure_ticket():
    from app.agents.answer_composer_agent import AnswerComposerAgent

    bundle = {
        "fact_lookup_presentation": {
            "primary_fact_need": "ticket_price",
            "ticket_price_facts": [
                {
                    "adult_price": 48.0,
                    "source_class": "ticket_platform",
                    "evidence_strength": "partial",
                }
            ],
            "lookup_claims": [
                {"claim_type": "ticket_price"},
                {"claim_type": "entrance_ticket_price"},
            ],
        }
    }
    assert AnswerComposerAgent._should_use_deterministic_ticket_fact_draft(bundle)

    mixed_bundle = {
        "fact_lookup_presentation": {
            "primary_fact_need": "ticket_price",
            "ticket_price_facts": [
                {
                    "adult_price": 48.0,
                    "source_class": "ticket_platform",
                    "evidence_strength": "partial",
                }
            ],
            "lookup_claims": [
                {"claim_type": "ticket_price"},
                {"claim_type": "opening_hours"},
            ],
        }
    }
    assert not AnswerComposerAgent._should_use_deterministic_ticket_fact_draft(mixed_bundle)

    web_only_bundle = {
        "fact_lookup_presentation": {
            "primary_fact_need": "ticket_price",
            "ticket_price_facts": [
                {
                    "adult_price": 0.0,
                    "source_class": "web",
                    "evidence_strength": "candidate_only",
                }
            ],
            "lookup_claims": [{"claim_type": "ticket_price"}],
        }
    }
    assert not AnswerComposerAgent._should_use_deterministic_ticket_fact_draft(web_only_bundle)


def test_ticket_fact_ranking_hides_web_candidates_when_platform_price_exists():
    from app.orchestrator.fact_lookup_guided_composition import _rank_ticket_price_facts

    rows = _rank_ticket_price_facts(
        [
            {
                "ticket_name": "大门票 成人票",
                "adult_price": 48.0,
                "source_class": "ticket_platform",
                "evidence_strength": "partial",
                "source_url": "https://a.feizhu.com/x",
            },
            {
                "ticket_name": "ticket price",
                "adult_price": 50.0,
                "source_class": "web",
                "evidence_strength": "candidate_only",
                "source_url": "https://example.com/search",
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["adult_price"] == 48.0


def test_ticket_charge_policy_does_not_turn_internal_platform_price_into_area_fee():
    from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft
    from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType

    frame = _frame("夫子庙需要收费吗", needs=["ticket_price"], places=["夫子庙"])
    state = _state(frame)
    state.evidence = [
        Evidence(
            source_name="open-webSearch",
            source_type=SourceType.WEB,
            country="China",
            city="南京",
            place_name="夫子庙",
            confidence=0.5,
            claims=[
                Claim(
                    claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                    value="夫子庙步行街和秦淮风光带开放区域免费开放，内部景点和体验项目需另行购票。",
                    confidence=0.5,
                )
            ],
        ),
        Evidence(
            source_name="Fliggy FlyAI",
            source_type=SourceType.TICKET_PLATFORM,
            source_url="https://a.feizhu.com/4gREbJ",
            country="China",
            city="南京",
            place_name="夫子庙",
            confidence=0.62,
            claims=[
                Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="¥29", confidence=0.62),
                Claim(claim_type=ClaimType.TICKET_TYPE, value="大门票 成人票", confidence=0.55),
            ],
        ),
    ]

    draft = build_fact_lookup_draft(state)
    text = draft.render_text()

    assert "夫子庙是否收费" in text
    assert "免费开放" in text
    assert "不能据此认定夫子庙开放区域整体收费" in text
    assert "0 CNY" not in text
    assert "29 CNY" in text
    assert "夫子庙门票价格：\n- 当前证据中包含夫子庙门票价格线索" not in text


def test_fliggy_ticket_title_is_not_duplicated_after_normalization():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_evidence
    from tools.ticketing.evidence_normalizer import normalize_fliggy_ticket_payload

    evidence = normalize_fliggy_ticket_payload(
        {
            "items": [
                {
                    "ticket_title": "夫子庙大成殿",
                    "ticket_name": "大门票 成人票",
                    "ticket_type": "夫子庙大成殿 - 大门票 成人票",
                    "price_text": "¥29",
                    "platform_ticket_url": "https://a.feizhu.com/4AiiMH",
                    "source": "fliggy_flyai_cli",
                }
            ]
        },
        place_name="夫子庙",
        city="南京",
        country="China",
    )

    facts = extract_ticket_price_from_evidence(evidence, claim_type="ticket_price")

    assert facts
    assert facts[0].ticket_name == "夫子庙大成殿 - 大门票 成人票"
    assert facts[0].summary_line().count("夫子庙大成殿") == 1
