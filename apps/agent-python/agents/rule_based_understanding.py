from datetime import date

from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.catalog.place_resolver import PlaceResolver
from app.schemas.conversation_context import ConversationContext
from app.schemas.place_candidate import PlaceCandidate
from app.schemas.place_context import PlaceContext
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_profile import UserProfile
from app.schemas.user_query import PartyType, PaceType, UserContext


DEICTIC_MARKERS = ["这里", "这边", "那边", "此处", "此地", "这个景点", "这个地方", "刚才那个", "上面那个", "here", "this place", "that place"]
TIME_FOLLOWUP_MARKERS = ["明天", "那明天", "后天", "今天", "tomorrow", "today"]
SEMANTIC_LOW_CONFIDENCE_MARKERS = ["踩雷", "会不会", "累不累", "值不值", "overrated", "tiring"]
ITINERARY_MARKERS = ["安排", "行程", "一天", "半日", "路线", "轻松玩", "文化游"]
COMPARE_MARKERS = ["哪个更", "哪个适合", "比较", "对比", "vs", "还是"]
CROWD_MARKERS = ["人流量", "人多", "拥挤", "排队", "crowd", "busy", "queue"]
BEST_TIME_MARKERS = ["几月", "什么时候", "何时", "最佳时间", "适合几月"]
CONCERN_PATTERNS: list[tuple[list[str], str]] = [
    (["人流量", "人多", "拥挤", "排队", "crowd", "busy", "queue"], "crowd_level"),
    (["累不累", "走路", "坡", "步行", "tiring", "walk", "slope"], "walking_intensity"),
    (["爸妈", "父母", "老人", "长辈", "elderly", "senior"], "elderly_suitability"),
    (["婴儿车", "推车", "stroller", "轮椅", "无障碍", "accessibility"], "accessibility"),
    (["休息", "歇脚", "rest area", "bench"], "nearby_rest_area"),
    (["和服", "kimono"], "mobility_dress"),
    (["踩雷", "overrated", "失望"], "overrated_risk"),
    (["天气", "下雨", "weather", "rain"], "weather"),
    (["吃", "餐厅", "food", "restaurant"], "nearby_food"),
]


class RuleBasedUnderstanding:
    """Deterministic query understanding — no facts, no answers."""

    @classmethod
    def understand(
        cls,
        raw_query: str,
        context: ConversationContext,
        user_ctx: UserContext | None = None,
    ) -> QueryUnderstandingResult:
        text = raw_query.strip()
        resolved: dict[str, str] = {}
        assumptions: list[str] = []
        missing: list[str] = []
        concerns: list[str] = []
        unresolved: list[str] = []
        rewritten = text
        followup_used = False

        for markers, concern_key in CONCERN_PATTERNS:
            if any(m in text.lower() or m in text for m in markers):
                if concern_key not in concerns:
                    concerns.append(concern_key)

        candidates = PlaceResolver.resolve_sync(text, context)
        place_from_query = [
            c.canonical_name or c.mention for c in candidates if c.is_poi and (c.canonical_name or c.mention)
        ]
        is_compare = any(m in text for m in COMPARE_MARKERS) or len(place_from_query) >= 2
        has_deictic = any(m in text for m in DEICTIC_MARKERS) or any(m in text.lower() for m in ["here", "this place", "that place"])
        is_time_followup = any(m in text for m in TIME_FOLLOWUP_MARKERS) and not place_from_query

        resolved_place: str | None = None
        places: list[PlaceContext] = []

        if has_deictic:
            if context.last_places:
                pc = context.last_places[-1]
                resolved_place = pc.canonical_name
                places = [pc]
                for marker in DEICTIC_MARKERS:
                    if marker in rewritten:
                        rewritten = rewritten.replace(marker, resolved_place)
                resolved["这里"] = resolved_place
                resolved["here"] = resolved_place
                followup_used = True
            else:
                unresolved.append("这里")
                return cls._clarification(
                    text,
                    concerns,
                    "你指的是哪个景点或区域？我需要先知道地点，才能判断人流量或拥挤风险。",
                    ["place_reference"],
                )
        elif is_time_followup and context.last_places:
            pc = context.last_places[-1]
            resolved_place = pc.canonical_name
            places = [pc]
            resolved["place"] = resolved_place
            followup_used = True
            if "明天" in text or "tomorrow" in text.lower():
                resolved["travel_date"] = "tomorrow"
                assumptions.append("将「明天」解析为出行日期 tomorrow。")
                rewritten = f"{resolved_place} 明天是否适合前往（天气与开放风险）"
                if "weather" not in concerns:
                    concerns.append("weather")
            else:
                assumptions.append("继承上一轮景点上下文，更新出行时间假设。")
                rewritten = f"{resolved_place} 在指定日期的出行评估"
        elif place_from_query:
            places = []
            for c in candidates:
                if c.is_poi:
                    places.append(c.to_place_context())
            resolved_place = places[0].canonical_name
            resolved["place"] = resolved_place

        if is_compare and place_from_query:
            rewritten = f"比较以下景点：{', '.join(place_from_query)}"
            places = [c.to_place_context() for c in candidates if c.is_poi]

        if "适合" in text and any(x in text for x in ["爸妈", "父母", "老人", "长辈", "elderly"]) and not is_compare:
            target = resolved_place or (place_from_query[0] if place_from_query else None)
            if target:
                rewritten = f"{target} 是否适合带长辈游览（关注步行强度、无障碍、人流、交通）"
            concerns.extend(["elderly_suitability", "walking_intensity", "accessibility", "crowd_level", "transit"])

        if any(k in text for k in CROWD_MARKERS):
            target = resolved_place or (place_from_query[0] if place_from_query else None)
            if target:
                rewritten = f"{target} 的人流/拥挤程度（需基于评价与热门程度估算，非实时数据）"
            concerns.append("crowd_level")
            if "queue_time" not in concerns:
                concerns.append("queue_time")

        if "踩雷" in text or "overrated" in text.lower():
            concerns.extend(["overrated_risk", "crowd_level", "value_for_money"])
            if not resolved_place and not context.last_places:
                unresolved.append("这个地方")
                return cls._clarification(
                    text,
                    concerns,
                    "你指的是哪个景点？我需要知道具体地点，才能结合评价判断是否存在「踩雷」风险。",
                    ["place_reference"],
                )
            if context.last_places and not resolved_place:
                places = [context.last_places[-1]]
                resolved_place = places[0].canonical_name
                resolved["这个地方"] = resolved_place
                followup_used = True
                rewritten = f"{resolved_place} 是否存在踩雷/名不副实风险（基于评价维度，非事实断言）"

        if "换成" in text and ("老人" in text or "友好" in text):
            if context.last_places:
                places = context.last_places
                resolved_place = places[0].canonical_name
                followup_used = True
                assumptions.append("继承上一轮景点/行程，更新用户画像为更偏老人友好。")
                rewritten = f"{resolved_place} 老人友好度与体力要求评估"

        profile = cls._build_profile(text, user_ctx, context)
        if "老人" in text or "友好" in text:
            if "elderly" not in profile.party:
                profile.party.append("elderly")
            profile.pace = profile.pace or "relaxed"

        country = context.last_country
        city = context.last_city
        travel_date = context.last_travel_date or (user_ctx.travel_date if user_ctx else None)
        if resolved.get("travel_date") == "tomorrow":
            travel_date = "tomorrow"
        if places:
            country = places[0].country or country
            city = places[0].city or city
        elif not country or not city:
            city_hit = next((c for c in candidates if c.is_city), None)
            if city_hit:
                country = city_hit.country or country
                city = city_hit.city or city_hit.canonical_name or city

        is_best_time_city = (
            not places
            and any(m in text for m in BEST_TIME_MARKERS)
            and "几点" not in text
            and "关门" not in text
        )
        if is_best_time_city:
            task_type = TravelTaskType.OPEN_ENDED_ADVICE
            if "seasonality" not in concerns:
                concerns.append("seasonality")
            rewritten = f"{city or country or '目的地'} 最佳出行季节/月份建议（基于一般季节规律）"
            confidence = 0.82 if (city or country) else 0.55
        else:
            task_type = cls._detect_task_type(
                text, concerns, is_compare, place_from_query, context, is_time_followup
            )
            confidence = 0.9 if (resolved_place or place_from_query) else 0.65

        required, optional = cls._evidence_for_task(task_type, concerns)

        if "京都" in text or (city == "Kyoto"):
            assumptions.append("默认目的地城市为 Kyoto, Japan。") if city == "Kyoto" else None
        if "父母" in text or "爸妈" in text:
            assumptions.append("默认同行人包含长辈，pace 偏轻松。")

        if assumptions:
            confidence = min(confidence, 0.88)
        if any(m in text for m in SEMANTIC_LOW_CONFIDENCE_MARKERS):
            confidence = min(confidence, 0.74)

        task = TravelTask(
            task_type=task_type,
            rewritten_query=rewritten,
            country=country or (places[0].country if places else None),
            city=city or (places[0].city if places else None),
            places=places,
            travel_date=travel_date,
            start_location=user_ctx.start_location if user_ctx else None,
            user_profile=profile,
            key_concerns=list(dict.fromkeys(concerns)),
            required_evidence=required,
            optional_evidence=optional,
            assumptions=assumptions,
            followup_context_used=followup_used,
            confidence=confidence,
        )

        qu = QueryUnderstandingResult(
            rewritten_query=rewritten,
            travel_task=task,
            resolved_references=resolved,
            missing_critical_info=missing,
            needs_clarification=False,
            assumptions=assumptions,
            confidence=confidence,
            key_concerns=task.key_concerns,
            semantic_frame=(
                SemanticFrameBuilder.build_city_best_time(text, country, city, rewritten, confidence)
                if is_best_time_city and country and city
                else None
            ),
        )
        if qu.semantic_frame is not None:
            return qu
        return SemanticFrameBuilder.ensure_result(text, qu, candidates)

    @staticmethod
    def _build_profile(text: str, user_ctx: UserContext | None, context: ConversationContext) -> UserProfile:
        party: list[str] = []
        if user_ctx and user_ctx.party:
            party = [p.value for p in user_ctx.party]
        elif context.last_user_profile:
            party = list(context.last_user_profile.party)
        if any(x in text for x in ["父母", "爸妈", "老人", "长辈"]):
            if "elderly" not in party:
                party.append("elderly")
        pace = user_ctx.pace.value if user_ctx and user_ctx.pace != PaceType.UNKNOWN else None
        if context.last_user_profile and not pace:
            pace = context.last_user_profile.pace
        if any(x in text for x in ["轻松", "别太累"]):
            pace = "relaxed"
        return UserProfile(
            party=party,
            pace=pace,
            preferences=(user_ctx.preferences if user_ctx else []) or (context.last_user_profile.preferences if context.last_user_profile else []),
            budget_level=user_ctx.budget_level.value if user_ctx else None,
            transport_preference=user_ctx.transport_preference.value if user_ctx else None,
        )

    @classmethod
    def _detect_task_type(
        cls,
        text: str,
        concerns: list[str],
        is_compare: bool,
        place_from_query: list[str],
        context: ConversationContext,
        is_time_followup: bool,
    ) -> TravelTaskType:
        if any(m in text for m in CROWD_MARKERS):
            return TravelTaskType.CROWD_INQUIRY
        if is_compare:
            return TravelTaskType.COMPARE_PLACES
        if any(m in text for m in ITINERARY_MARKERS):
            return TravelTaskType.ITINERARY_PLANNING
        if is_time_followup:
            return TravelTaskType.WEATHER_RISK if "weather" in concerns else TravelTaskType.PLACE_FACT_LOOKUP
        if "overrated_risk" in concerns:
            return TravelTaskType.SINGLE_PLACE_SUITABILITY
        if "elderly_suitability" in concerns or any(x in text for x in ["父母", "爸妈", "老人"]):
            return TravelTaskType.SINGLE_PLACE_SUITABILITY
        if "crowd_level" in concerns and place_from_query:
            return TravelTaskType.CROWD_INQUIRY
        if place_from_query:
            return TravelTaskType.SINGLE_PLACE_SUITABILITY
        if context.last_task_type:
            try:
                return TravelTaskType(context.last_task_type)
            except ValueError:
                pass
        return TravelTaskType.OPEN_ENDED_ADVICE

    @staticmethod
    def _evidence_for_task(task_type: TravelTaskType, concerns: list[str]) -> tuple[list[str], list[str]]:
        mapping = {
            TravelTaskType.CROWD_INQUIRY: (["crowd_level", "queue_time"], ["event", "weather", "reservation_policy"]),
            TravelTaskType.SINGLE_PLACE_SUITABILITY: (
                ["walking_intensity", "accessibility", "crowd_level", "transit"],
                ["official_hours", "weather", "nearby_rest_area"],
            ),
            TravelTaskType.COMPARE_PLACES: (["crowd_level", "walking_intensity", "transit"], ["official_hours"]),
            TravelTaskType.WEATHER_RISK: (["weather"], ["crowd_level", "official_hours"]),
            TravelTaskType.PLACE_FACT_LOOKUP: (["official_hours", "weather"], ["crowd_level"]),
        }
        return mapping.get(task_type, (["official_hours"], ["transit", "reviews"]))

    @staticmethod
    def _clarification(
        raw: str,
        concerns: list[str],
        question: str,
        missing: list[str],
    ) -> QueryUnderstandingResult:
        task = TravelTask(rewritten_query=raw, key_concerns=concerns, confidence=0.3)
        qu = QueryUnderstandingResult(
            rewritten_query=raw,
            travel_task=task,
            missing_critical_info=missing,
            needs_clarification=True,
            clarification_question=question,
            confidence=0.3,
            key_concerns=concerns,
        )
        return SemanticFrameBuilder.ensure_result(raw, qu)

    @staticmethod
    def needs_llm(text: str, result: QueryUnderstandingResult) -> bool:
        if result.needs_clarification:
            return False
        if result.confidence >= 0.75 and not any(m in text for m in SEMANTIC_LOW_CONFIDENCE_MARKERS):
            return False
        return any(m in text for m in SEMANTIC_LOW_CONFIDENCE_MARKERS) or result.confidence < 0.75
