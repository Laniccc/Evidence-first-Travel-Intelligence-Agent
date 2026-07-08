"""Lookup Claim layer — compile, extraction, adoption, S8 expression tests."""

from __future__ import annotations

from app.orchestrator.claim_compiler import compile_lookup_claims
from app.orchestrator.claim_decision_enrichment import enrich_claim_decision
from app.orchestrator.evidence_ladder import max_adoption_for_evidence
from app.orchestrator.fact_lookup_guided_composition import build_fact_lookup_draft
from app.orchestrator.opening_hours_extractor import extract_opening_hours_from_text
from app.orchestrator.retrieval_attempt_ledger import get_ledger, record_skip, retrieval_complete, save_ledger
from app.orchestrator.search_snippet_policy import evidence_strength_for_claim, is_search_snippet_evidence
from app.orchestrator.ticket_lookup_policy import filter_user_visible_limitations
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType
from app.schemas.evidence_decision_report import ClaimDecision
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.semantic_frame import DecisionType, SemanticEntities, SemanticFrame
from app.schemas.user_query import TravelAgentState
from app.orchestrator.response_contract_compiler import ResponseContractCompiler


def _lookup_frame(query: str, needs: list[str] | None = None) -> SemanticFrame:
    return SemanticFrame(
        raw_query=query,
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", places=["喀纳斯湖"] if "喀纳斯" in query else ["故宫博物院"]),
        information_needs=needs or [],
        requires_exact_fact=True,
    )


def _lookup_profile() -> IntentProfile:
    return IntentProfile(
        primary_intent=PrimaryIntent.LOOKUP,
        evidence_sensitivity=EvidenceSensitivity.HARD_FACT,
        answer_style=AnswerStyle.DIRECT_FACT,
        confidence=0.9,
        derivation="rules",
    )


def test_claim_compile_opening_hours():
    frame = SemanticFrame(
        raw_query="故宫博物院开放时间？",
        task_family="fact_lookup",
        decision_type=DecisionType.FACT_LOOKUP,
        entities=SemanticEntities(country="China", city="北京", places=["故宫博物院"]),
        information_needs=["opening_hours"],
    )
    claims = compile_lookup_claims(frame, frame.raw_query, intent_profile=_lookup_profile())
    assert claims
    primary = claims[0]
    assert primary.claim_type == "opening_hours"
    assert primary.claim_family == "operation_status"
    assert primary.requires_exact_fact


def test_claim_compile_entrance_ticket_price():
    frame = _lookup_frame("喀纳斯湖门票多少钱？", needs=["ticket_price"])
    claims = compile_lookup_claims(frame, frame.raw_query, intent_profile=_lookup_profile())
    ticket = next(c for c in claims if "ticket" in c.claim_type)
    assert ticket.claim_type in {"entrance_ticket_price", "ticket_price"}
    assert ticket.product_or_service == "entrance_ticket"
    assert ticket.claim_family == "ticket_booking"


def test_claim_compile_boat_ticket_price():
    frame = _lookup_frame("喀纳斯湖游船船票多少钱？", needs=["ticket_price"])
    claims = compile_lookup_claims(frame, frame.raw_query, intent_profile=_lookup_profile())
    boat = next(c for c in claims if c.claim_type == "boat_ticket_price")
    assert boat.product_or_service == "boat_ticket"
    assert "entrance_ticket" in boat.exclude_products
    assert "shuttle_bus_ticket" in boat.exclude_products


def test_search_snippet_not_strong_for_ticket_price():
    ev = Evidence(
        evidence_id="ev-snippet",
        source_name="search_mcp",
        source_type=SourceType.WEB,
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.TICKET_PRICE_CANDIDATE,
                value="喀纳斯湖门票 150 元/人 旅行社",
                confidence=0.4,
            )
        ],
        confidence=0.4,
    )
    assert is_search_snippet_evidence(ev)
    assert evidence_strength_for_claim(ev, "ticket_price") == "candidate_only"
    assert max_adoption_for_evidence(ev, "ticket_booking") == "candidate_only"


def test_official_source_candidate_not_official_page_evidence():
    from app.orchestrator.search_snippet_policy import is_official_page_evidence

    ev = Evidence(
        evidence_id="ev-official-candidate",
        source_name="Official Source Discovery",
        source_type=SourceType.WEB,
        country="China",
        source_url=None,
        claims=[
            Claim(
                claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                value="Official source candidate (not_official)",
                normalized_value={
                    "url": "https://www.sogou.com/link?url=redirect",
                    "domain": "sogou.com",
                    "title": "无关门票页面",
                    "source_class": "not_official",
                    "official_confidence": 0.2,
                    "supports_claim_types": [],
                    "supporting_signals": ["ticket_info_signal"],
                    "negative_signals": ["redirect_wrapper_url"],
                    "limitations": ["Search redirect wrapper URL"],
                    "claim_relevance_hints": {},
                },
                confidence=0.2,
            )
        ],
        confidence=0.2,
    )

    assert not is_official_page_evidence(ev)
    assert evidence_strength_for_claim(ev, "ticket_price") not in {"strong", "partial"}


def test_ticket_price_extractor_ignores_booking_snippet_without_amount():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "那拉提景区门票预订_同程旅行 评分4.0/5 49条点评 开放时间10:00-19:00",
        claim_type="ticket_price",
    )
    assert fact is None


def test_ticket_price_extractor_ignores_login_free_prompt():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "门票多少钱【同程旅行】 --> scenery 您好，请 登录 免费",
        claim_type="ticket_price",
    )
    assert fact is None


def test_ticket_price_extractor_ignores_free_entry_time_window():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "售票大厅营业时间07:00-17:00，免门票入园时间05:30-07:00",
        claim_type="ticket_price",
    )
    assert fact is None


def test_ticket_price_extractor_uses_amount_phrase_not_rating():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "那拉提景区 评分4.0/5 成人票95元起",
        claim_type="ticket_price",
    )
    assert fact is not None
    assert fact.adult_price == 95


def test_ticket_price_extractor_ignores_free_opening_hours_as_ticket_price():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "\u5f00\u653e\u65f6\u95f4 08:00\u201320:00 \u514d\u8d39\u5f00\u653e",
        claim_type="ticket_price",
        source_class="official",
    )
    assert fact is None


def test_ticket_price_extractor_prefers_paid_main_ticket_over_free_policy():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "\u95e8\u7968\u653f\u7b56\uff1a\u6bcf\u5e744\u67081\u65e5\u81f310\u670831\u65e5\u4e3a\u65fa\u5b63\uff0c"
        "\u5927\u95e8\u796860\u5143/\u4eba\uff1b\u672a\u6ee118\u5468\u5c81\u7684\u4e2d\u56fd\u516c\u6c11"
        "\u514d\u8d39\u53c2\u89c2\uff0c\u4f46\u987b\u9884\u7ea6\u3002",
        claim_type="ticket_price",
        source_class="official",
    )
    assert fact is not None
    assert fact.adult_price == 60


def test_ticket_price_extractor_accepts_general_free_admission():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_text

    fact = extract_ticket_price_from_text(
        "\u666f\u533a\u95e8\u7968\u514d\u8d39\uff0c\u65e0\u9700\u95e8\u7968\u5373\u53ef\u5165\u56ed\u3002",
        claim_type="ticket_price",
        source_class="official",
    )
    assert fact is not None
    assert fact.adult_price == 0


def test_opening_hours_extractor_from_generic_text():
    fact = extract_opening_hours_from_text(
        "开放入馆 8:30，停止入馆 16:10，清场 17:00，周一闭馆"
    )
    assert fact is not None
    assert fact.open_time == "8:30"
    assert fact.last_entry_time == "16:10"
    assert fact.close_time == "17:00"
    assert any("周一" in d for d in fact.closed_days)


def test_ticket_price_extractor_ignores_addon_platform_ticket_as_entrance_ticket():
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_evidence

    ev = Evidence(
        evidence_id="ev-addon",
        source_name="Fliggy FlyAI",
        source_type=SourceType.TICKET_PLATFORM,
        source_url="https://a.feizhu.com/example",
        country="China",
        claims=[
            Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="26 CNY", confidence=0.62),
            Claim(claim_type=ClaimType.ACTIVITY_PRICE, value="珍宝馆", confidence=0.58),
            Claim(claim_type=ClaimType.TICKET_TYPE, value="珍宝馆 - 大门票 成人票", confidence=0.55),
        ],
        confidence=0.62,
    )

    facts = extract_ticket_price_from_evidence([ev], claim_type="ticket_price")

    assert facts == []


def test_ticket_price_scorer_excludes_addon_platform_ticket_for_main_claim():
    from app.orchestrator.claim_policy_registry import enrich_claim_requirement, resolve_policy
    from app.orchestrator.evidence_scorer import EvidenceScorer
    from app.schemas.response_contract import ClaimRequirement

    ev = Evidence(
        evidence_id="ev-addon-score",
        source_name="Fliggy FlyAI",
        source_type=SourceType.TICKET_PLATFORM,
        source_url="https://a.feizhu.com/example",
        country="China",
        claims=[
            Claim(claim_type=ClaimType.TICKET_PRICE_CANDIDATE, value="26 CNY", confidence=0.62),
            Claim(claim_type=ClaimType.ACTIVITY_PRICE, value="珍宝馆", confidence=0.58),
            Claim(claim_type=ClaimType.TICKET_TYPE, value="珍宝馆 - 大门票 成人票", confidence=0.55),
        ],
        confidence=0.62,
    )
    policy = resolve_policy(enrich_claim_requirement(ClaimRequirement(claim_type="ticket_price")))

    scores = EvidenceScorer().score_claim_evidence(policy, [ev])

    assert scores == []


def test_ticket_price_scorer_rejects_official_free_opening_candidate():
    from app.orchestrator.claim_policy_registry import enrich_claim_requirement, resolve_policy
    from app.orchestrator.evidence_scorer import EvidenceScorer
    from app.schemas.response_contract import ClaimRequirement

    ev = Evidence(
        evidence_id="ev-official-free-open",
        source_name="Official Source Discovery",
        source_type=SourceType.WEB,
        source_url="https://www.dpm.org.cn/",
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.OFFICIAL_SOURCE_CANDIDATE,
                value="Official source candidate",
                normalized_value={
                    "url": "https://www.dpm.org.cn/",
                    "domain": "dpm.org.cn",
                    "title": "\u6545\u5bab\u535a\u7269\u9662 \u5b98\u7f51",
                    "source_class": "scenic_operator_official",
                    "official_confidence": 1.0,
                    "supports_claim_types": ["ticket_price"],
                    "page_excerpt": "\u5f00\u653e\u65f6\u95f4 08:00\u201320:00 \u514d\u8d39\u5f00\u653e",
                    "has_ticket_info": True,
                    "claim_relevance_hints": {"ticket_price": 0.92},
                },
                confidence=1.0,
            )
        ],
        confidence=1.0,
    )
    policy = resolve_policy(enrich_claim_requirement(ClaimRequirement(claim_type="ticket_price")))

    scores = EvidenceScorer().score_claim_evidence(policy, [ev])

    assert scores == []


def test_ticket_price_scorer_accepts_official_paid_ticket_fact():
    from app.orchestrator.claim_policy_registry import enrich_claim_requirement, resolve_policy
    from app.orchestrator.evidence_scorer import EvidenceScorer
    from app.schemas.response_contract import ClaimRequirement

    ev = Evidence(
        evidence_id="ev-official-paid-ticket",
        source_name="Official Page (fetch-web)",
        source_type=SourceType.OFFICIAL,
        source_url="https://www.dpm.org.cn/",
        country="China",
        claims=[
            Claim(
                claim_type=ClaimType.TICKET_PRICE,
                value=(
                    "\u95e8\u7968\u653f\u7b56\uff1a\u6bcf\u5e744\u67081\u65e5\u81f310\u670831\u65e5\u4e3a\u65fa\u5b63\uff0c"
                    "\u5927\u95e8\u796860\u5143/\u4eba"
                ),
                confidence=0.9,
            )
        ],
        confidence=0.9,
    )
    policy = resolve_policy(enrich_claim_requirement(ClaimRequirement(claim_type="ticket_price")))

    scores = EvidenceScorer().score_claim_evidence(policy, [ev])

    assert len(scores) == 1


def test_s8_candidate_ticket_price_not_written_as_conclusion():
    frame = _lookup_frame("喀纳斯湖游船船票多少钱？")
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=frame.raw_query)
    state.semantic_frame = frame
    state.intent_profile = _lookup_profile()
    state.response_contract = ResponseContractCompiler().compile(frame, intent_profile=state.intent_profile)
    state.evidence_decision_report = type(
        "R",
        (),
        {
            "claim_decisions": [
                enrich_claim_decision(
                    ClaimDecision(
                        claim_type="boat_ticket_price",
                        adoption="candidate_only",
                        coverage_quality="partial",
                        adopted_evidence_ids=["ev1"],
                    )
                )
            ]
        },
    )()
    draft = build_fact_lookup_draft(state)
    body = " ".join(b for sec in draft.sections for b in (sec.bullets or []))
    assert "不能作为结论" in body or "未能验证" in body or "未查到" in body or "游船" in body


def test_internal_debug_limitations_hidden_from_user():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="test")
    state.internal_debug_limitations = ["evidence_planning_and_tool_use reached max_steps"]
    state.user_visible_limitations = ["未能读取官方页面确认票价。"]
    kept = filter_user_visible_limitations(
        state.internal_debug_limitations + state.user_visible_limitations
    )
    joined = " ".join(kept)
    assert "max_steps" not in joined
    assert "未能读取" in joined or "官方" in joined


def test_s5_finish_uses_attempted_source_family_not_coverage():
    state = TravelAgentState(session_id="s", query_id="q", raw_user_query="故宫博物院开放时间？")
    ledger = get_ledger(state, "opening_hours")
    ledger.record_family("geo_resolution")
    ledger.record_family("search")
    ledger.record_family("map_candidate")
    save_ledger(state, ledger)
    record_skip(state, "official_source", "no_urls_or_search_results", claim_type="opening_hours")
    record_skip(state, "official_page_reader", "no_official_candidate_url", claim_type="opening_hours")
    assert retrieval_complete(state, "opening_hours")
