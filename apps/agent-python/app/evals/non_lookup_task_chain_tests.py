"""Minimal regression tests for non-lookup task-class state chains."""

from __future__ import annotations

from app.schemas.user_query import TravelAgentState, UserGoal
from app.orchestrator.intent_strategy_registry import resolve_intent_strategy
from app.orchestrator.non_lookup_task_chains import (
    build_minimal_clarification_question,
    build_non_lookup_task_debug_trace,
    build_non_lookup_task_draft,
    build_non_lookup_task_profile,
    collect_nearby_candidates,
    ensure_non_lookup_task_contract,
    evaluate_non_lookup_task_evidence,
    related_poi_not_disambiguation_same_scenic_area,
)
from app.schemas.evidence import Claim, ClaimType, DataFreshness, Evidence, SourceType
from app.schemas.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent
from app.schemas.place_ambiguity import PlaceAmbiguityCandidate, PlaceAmbiguityInfo
from app.schemas.semantic_frame import DecisionType, SemanticFrame, TaskFamily


def _state(
    intent: PrimaryIntent,
    query: str,
    *,
    places: list[str] | None = None,
    needs: list[str] | None = None,
) -> TravelAgentState:
    frame = SemanticFrame(raw_query=query, normalized_request=query)
    frame.entities.country = "China"
    frame.entities.city = "测试市"
    frame.entities.places = places or ["测试景区"]
    frame.information_needs = needs or []
    if intent == PrimaryIntent.ADVISORY:
        frame.task_family = TaskFamily.ADVISORY
        sensitivity = EvidenceSensitivity.MODEL_PRIOR_ALLOWED
        style = AnswerStyle.ADVISORY
    elif intent == PrimaryIntent.REVIEW_CHECK:
        frame.task_family = TaskFamily.ADVISORY
        sensitivity = EvidenceSensitivity.EXPERIENCE_BASED
        style = AnswerStyle.ADVISORY
    elif intent == PrimaryIntent.PLANNING:
        frame.task_family = TaskFamily.PLANNING
        frame.decision_type = DecisionType.ROUTE_PLAN
        sensitivity = EvidenceSensitivity.EVIDENCE_PREFERRED
        style = AnswerStyle.ITINERARY
    elif intent == PrimaryIntent.COMPARISON:
        frame.task_family = TaskFamily.COMPARISON
        sensitivity = EvidenceSensitivity.EVIDENCE_PREFERRED
        style = AnswerStyle.COMPARISON
    elif intent == PrimaryIntent.NEARBY:
        frame.decision_type = DecisionType.NEARBY_SEARCH
        sensitivity = EvidenceSensitivity.EVIDENCE_PREFERRED
        style = AnswerStyle.RECOMMENDATION_LIST
    elif intent == PrimaryIntent.REALTIME_CHECK:
        frame.requires_live_data = True
        frame.task_family = TaskFamily.WEATHER
        sensitivity = EvidenceSensitivity.LIVE_REQUIRED
        style = AnswerStyle.DIRECT_FACT
    else:
        frame.needs_clarification = True
        frame.missing_slots = ["place"]
        sensitivity = EvidenceSensitivity.EVIDENCE_PREFERRED
        style = AnswerStyle.CLARIFICATION

    state = TravelAgentState(session_id="s", query_id="q", raw_user_query=query)
    state.semantic_frame = frame
    state.intent_profile = IntentProfile(
        primary_intent=intent,
        evidence_sensitivity=sensitivity,
        answer_style=style,
        requires_live_data=intent == PrimaryIntent.REALTIME_CHECK,
        requires_review_signal=intent in {PrimaryIntent.ADVISORY, PrimaryIntent.REVIEW_CHECK},
        requires_route_planning=intent == PrimaryIntent.PLANNING,
    )
    state.intent_strategy = resolve_intent_strategy(state.intent_profile)
    ensure_non_lookup_task_contract(state)
    return state


def _evidence(
    source: str,
    source_type: SourceType,
    claim_type: ClaimType,
    value: str,
    *,
    place: str = "测试景区",
    confidence: float = 0.8,
    freshness: DataFreshness = DataFreshness.RECENT,
    normalized_value=None,
) -> Evidence:
    return Evidence(
        source_name=source,
        source_type=source_type,
        country="China",
        city="测试市",
        place_name=place,
        data_freshness=freshness,
        confidence=confidence,
        claims=[
            Claim(
                claim_type=claim_type,
                value=value,
                normalized_value=normalized_value,
                confidence=confidence,
            )
        ],
    )


def test_advisory_uses_review_and_context_not_hard_fact_only():
    state = _state(PrimaryIntent.ADVISORY, "冬天值得去测试景区吗？")
    state.evidence = [
        _evidence("review_a", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "冬季体验评价两极分化"),
        _evidence("season", SourceType.WEB, ClaimType.SEASONALITY, "冬季风景好但天气冷"),
    ]
    report = evaluate_non_lookup_task_evidence(state)
    trace = build_non_lookup_task_debug_trace(state, report)

    assert trace.task_class == "advisory"
    assert "review_platform_provider" in trace.source_family_plan
    assert any(d.claim_type == "review_summary" and d.adoption != "refuse_to_guess" for d in report.claim_decisions)


def test_advisory_splits_hard_fact_subclaim():
    state = _state(PrimaryIntent.ADVISORY, "测试景区值得去吗，门票贵不贵？")
    state.evidence = [
        _evidence("prior", SourceType.MODEL_PRIOR, ClaimType.TICKET_PRICE, "大约 100 元"),
        _evidence("review", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "多数人认为风景不错"),
    ]
    report = evaluate_non_lookup_task_evidence(state)

    ticket = next(d for d in report.claim_decisions if d.claim_type == "ticket_price")
    assert ticket.adoption == "refuse_to_guess"
    assert not ticket.adopted_evidence_ids


def test_advisory_composer_shows_suitable_and_not_suitable():
    state = _state(PrimaryIntent.ADVISORY, "测试景区适合带老人吗？")
    state.evidence = [
        _evidence("review", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "老人同行需要注意台阶"),
    ]
    report = evaluate_non_lookup_task_evidence(state)
    draft = build_non_lookup_task_draft(state, report)

    titles = [s.title for s in draft.sections]
    assert "Suitable for" in titles
    assert "Not suitable for" in titles


def test_review_check_collects_multi_source_review_signal():
    state = _state(PrimaryIntent.REVIEW_CHECK, "测试景区是不是商业化严重？")
    state.evidence = [
        _evidence("dianping", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "商业化评价较多"),
        _evidence("ctrip", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_ASPECT, "游客提到店铺密集"),
    ]
    report = evaluate_non_lookup_task_evidence(state)

    review = next(d for d in report.claim_decisions if d.claim_type == "review_summary")
    assert "multi_source_consistent" in review.reason
    assert review.adoption == "adopt"


def test_review_check_rejects_single_extreme_review_as_global_claim():
    state = _state(PrimaryIntent.REVIEW_CHECK, "测试景区是不是很坑？")
    state.evidence = [
        _evidence("one_review", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "最差，千万别去"),
    ]
    report = evaluate_non_lookup_task_evidence(state)

    review = next(d for d in report.claim_decisions if d.claim_type == "review_summary")
    assert "anecdotal_only" in review.reason
    assert review.adoption == "adopt_with_limitation"
    assert review.must_show_limitation


def test_review_insight_composer_outputs_review_tendency():
    state = _state(PrimaryIntent.REVIEW_CHECK, "游客评价怎么样？")
    state.evidence = [
        _evidence("review", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "正面集中在景色，负面集中在人多"),
    ]
    report = evaluate_non_lookup_task_evidence(state)
    draft = build_non_lookup_task_draft(state, report)

    assert draft.compose_mode == "review_insight"
    assert any(section.title == "Review tendency" for section in draft.sections)


def test_planning_requires_origin_when_missing():
    state = _state(PrimaryIntent.PLANNING, "一天往返来得及吗？", places=["测试景区"], needs=["route_plan"])
    state.evidence = []
    report = evaluate_non_lookup_task_evidence(state)

    route = next(d for d in report.claim_decisions if d.claim_type == "route_plan")
    assert route.adoption == "ask_clarification"
    assert "missing_origin" in route.reason


def test_planning_uses_route_matrix_and_opening_hours():
    state = _state(PrimaryIntent.PLANNING, "A 到 B 一天怎么玩？", places=["A", "B"], needs=["route_plan", "opening_hours"])
    state.user_goal = UserGoal(start_location="A")
    state.evidence = [
        _evidence("route", SourceType.MAP, ClaimType.DURATION, "驾车 90 分钟", place="B"),
        _evidence("official", SourceType.OFFICIAL, ClaimType.OPENING_HOURS, "09:00-17:00", place="B"),
    ]
    report = evaluate_non_lookup_task_evidence(state)
    trace = build_non_lookup_task_debug_trace(state, report)

    assert "baidu_route_mcp" in trace.allowed_tools
    assert any(d.claim_type in {"duration", "opening_hours"} and d.adoption != "refuse_to_guess" for d in report.claim_decisions)


def test_itinerary_composer_outputs_time_blocks():
    state = _state(PrimaryIntent.PLANNING, "A 到 B 一天怎么玩？", places=["A", "B"], needs=["route_plan"])
    state.user_goal = UserGoal(start_location="A")
    state.evidence = [_evidence("route", SourceType.MAP, ClaimType.DURATION, "车程 90 分钟", place="B")]
    report = evaluate_non_lookup_task_evidence(state)
    draft = build_non_lookup_task_draft(state, report)

    assert draft.compose_mode == "itinerary"
    assert any(section.title == "Time blocks" for section in draft.sections)


def test_comparison_builds_per_place_claims():
    state = _state(PrimaryIntent.COMPARISON, "A 和 B 哪个更值得去？", places=["A", "B"], needs=["review_summary"])
    profile = build_non_lookup_task_profile(state)

    assert profile is not None
    assert profile.task_class == "comparison"
    assert profile.retrieval_mode == "multi_place_parallel"


def test_comparison_requires_aligned_dimensions():
    state = _state(PrimaryIntent.COMPARISON, "A 和 B 哪个更值得去？", places=["A", "B"], needs=["review_summary"])
    state.evidence = [
        _evidence("review_a", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "A 风景好", place="A")
    ]
    report = evaluate_non_lookup_task_evidence(state)

    review = next(d for d in report.claim_decisions if d.claim_type == "review_summary")
    assert review.adoption == "refuse_to_guess"
    assert "evidence_asymmetry" in review.reason


def test_comparison_composer_reports_evidence_asymmetry():
    state = _state(PrimaryIntent.COMPARISON, "A 和 B 哪个更适合亲子？", places=["A", "B"], needs=["review_summary"])
    state.evidence = [_evidence("review_a", SourceType.REVIEW_PLATFORM, ClaimType.REVIEW_SUMMARY, "A 亲子友好", place="A")]
    report = evaluate_non_lookup_task_evidence(state)
    draft = build_non_lookup_task_draft(state, report)

    assert draft.compose_mode == "compare"
    assert any(section.title == "Evidence asymmetry" for section in draft.sections)


def test_nearby_food_maps_to_nearby_recommendation():
    state = _state(PrimaryIntent.NEARBY, "附近有什么吃饭的地方？", needs=["nearby_food"])
    profile = build_non_lookup_task_profile(state)

    assert profile is not None
    assert profile.task_class == "nearby"
    assert "nearby_recommendation" in profile.information_domains


def test_nearby_filters_far_or_wrong_category_poi():
    accepted = _evidence(
        "map",
        SourceType.MAP,
        ClaimType.FOOD,
        "近处餐厅",
        normalized_value={"name": "近处餐厅", "category": "food", "distance_m": 450},
    )
    far = _evidence(
        "map",
        SourceType.MAP,
        ClaimType.FOOD,
        "远处餐厅",
        normalized_value={"name": "远处餐厅", "category": "food", "distance_m": 5200},
    )
    wrong = _evidence(
        "map",
        SourceType.MAP,
        ClaimType.FOOD,
        "纪念品店",
        normalized_value={"name": "纪念品店", "category": "shop", "distance_m": 300, "category_match": False},
    )

    candidates = collect_nearby_candidates([accepted, far, wrong])
    assert [c.name for c in candidates if c.accepted] == ["近处餐厅"]


def test_nearby_composer_outputs_distance_and_reason():
    state = _state(PrimaryIntent.NEARBY, "附近有什么吃饭的地方？", needs=["nearby_food"])
    state.evidence = [
        _evidence(
            "map",
            SourceType.MAP,
            ClaimType.FOOD,
            "近处餐厅",
            normalized_value={"name": "近处餐厅", "category": "food", "distance_m": 450, "reason": "步行可达"},
        )
    ]
    report = evaluate_non_lookup_task_evidence(state)
    draft = build_non_lookup_task_draft(state, report)

    text = "\n".join("\n".join(s.bullets) for s in draft.sections)
    assert "450" in text
    assert "步行可达" in text


def test_realtime_requires_fresh_data():
    state = _state(PrimaryIntent.REALTIME_CHECK, "今天路况怎么样？", needs=["traffic_status"])
    state.evidence = [
        _evidence(
            "traffic",
            SourceType.MAP,
            ClaimType.TRAFFIC_STATUS,
            "当前通行正常",
            freshness=DataFreshness.LIVE,
        )
    ]
    report = evaluate_non_lookup_task_evidence(state)

    traffic = next(d for d in report.claim_decisions if d.claim_type == "traffic_status")
    assert traffic.adoption == "adopt"
    assert "freshness_checked" in traffic.reason


def test_realtime_rejects_model_prior_for_live_status():
    state = _state(PrimaryIntent.REALTIME_CHECK, "今天开放吗？", needs=["current_weather"])
    state.evidence = [
        _evidence("prior", SourceType.MODEL_PRIOR, ClaimType.WEATHER, "通常天气不错", freshness=DataFreshness.STALE)
    ]
    report = evaluate_non_lookup_task_evidence(state)

    weather = next(d for d in report.claim_decisions if d.claim_type == "current_weather")
    assert weather.adoption == "refuse_to_guess"
    assert not weather.adopted_evidence_ids


def test_realtime_composer_includes_freshness_note():
    state = _state(PrimaryIntent.REALTIME_CHECK, "明天天气怎么样？", needs=["current_weather"])
    state.evidence = [
        _evidence("weather", SourceType.WEATHER_API, ClaimType.WEATHER, "明天小雨", freshness=DataFreshness.RECENT)
    ]
    report = evaluate_non_lookup_task_evidence(state)
    draft = build_non_lookup_task_draft(state, report)

    assert draft.compose_mode == "realtime_status"
    assert any(section.title == "Freshness note" for section in draft.sections)


def test_clarification_for_missing_place():
    state = _state(PrimaryIntent.CLARIFICATION, "那里附近有什么？", places=[], needs=[])
    report = evaluate_non_lookup_task_evidence(state)
    question = build_minimal_clarification_question(state)

    assert report.claim_decisions[0].adoption == "ask_clarification"
    assert "place" in question.lower()


def test_place_disambiguation_for_true_ambiguous_place():
    state = _state(PrimaryIntent.CLARIFICATION, "南山好玩吗？", places=["南山"], needs=[])
    assert state.semantic_frame is not None
    state.semantic_frame.place_ambiguity = PlaceAmbiguityInfo(
        is_ambiguous=True,
        candidates=[
            PlaceAmbiguityCandidate(name="南山", region="广东", city="深圳"),
            PlaceAmbiguityCandidate(name="南山", region="重庆", city="重庆"),
        ],
    )
    report = evaluate_non_lookup_task_evidence(state)
    question = build_minimal_clarification_question(state)

    assert report.claim_decisions[0].claim_type == "disambiguation"
    assert "深圳" in question and "重庆" in question


def test_related_poi_not_disambiguation_same_scenic_area():
    state = _state(PrimaryIntent.CLARIFICATION, "景区附近有什么？", places=["测试景区"], needs=[])
    state.structured_result = {
        "place_disambiguation_candidates": [
            {"name": "东门", "city": "测试市", "parent_place": "测试景区"},
            {"name": "游客中心", "city": "测试市", "parent_place": "测试景区"},
        ]
    }
    report = evaluate_non_lookup_task_evidence(state)

    assert related_poi_not_disambiguation_same_scenic_area(state)
    assert report.claim_decisions[0].claim_type == "related_poi_ranking"
