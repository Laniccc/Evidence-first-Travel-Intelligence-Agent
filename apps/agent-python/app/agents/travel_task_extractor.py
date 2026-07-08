from app.catalog.place_catalog import get_place_catalog
from app.orchestrator.information_need_aliases import infer_all_nearby_needs_from_text
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.place_context import PlaceContext
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_profile import UserProfile
from app.schemas.user_query import IntentType, UserContext, UserGoal


class TravelTaskExtractor:
    CROWD_MARKERS = ["人流量", "人多", "拥挤", "排队", "crowd", "busy", "queue"]
    COMPARE_MARKERS = ["哪个更", "哪个适合", "比较", "对比", "vs", "还是"]
    ITINERARY_MARKERS = ["安排", "行程", "一天", "半日", "路线", "轻松玩", "文化游"]
    WEATHER_MARKERS = ["天气", "下雨", "rain", "weather"]
    FOOD_MARKERS = ["吃", "餐厅", "美食", "food", "restaurant"]
    LODGING_MARKERS = ["住宿", "酒店", "lodging", "hotel"]
    TRANSPORT_MARKERS = ["怎么去", "交通", "地铁", "transit", "bus"]

    @classmethod
    def extract(
        cls,
        rewritten: RewrittenQueryResult,
        memory: ConversationMemory,
        goal: UserGoal,
        place_contexts: list[PlaceContext] | None = None,
    ) -> TravelTask:
        catalog = get_place_catalog()
        text = rewritten.rewritten_query
        raw_lower = text.lower()

        task_type = cls._detect_task_type(text, goal, rewritten.key_concerns)
        places = place_contexts or [catalog.resolve_place_context(p) for p in goal.place_candidates]

        if rewritten.resolved_references.get("here") and not places:
            canonical = catalog.normalize_place_name(rewritten.resolved_references["here"]) or rewritten.resolved_references["here"]
            places = [catalog.resolve_place_context(canonical)]

        country = goal.destination_country or memory.last_country
        city = goal.destination_city or memory.last_city
        if places and places[0].country:
            country = places[0].country
        if places and places[0].city:
            city = places[0].city

        profile = UserProfile(
            party=[p.value for p in goal.party],
            pace=goal.pace.value if goal.pace.value != "unknown" else None,
            preferences=goal.preferences,
            budget_level=goal.budget_level.value,
        )

        required, optional = cls._evidence_for_task(task_type, rewritten.key_concerns, text=text)

        return TravelTask(
            task_type=task_type,
            rewritten_query=text,
            country=country,
            city=city,
            places=places,
            travel_date=goal.travel_date or memory.travel_date,
            start_location=goal.start_location,
            user_profile=profile,
            key_concerns=rewritten.key_concerns,
            required_evidence=required,
            optional_evidence=optional,
            constraints=goal.constraints,
            assumptions=list(rewritten.assumptions),
            followup_context_used=bool(rewritten.resolved_references),
            confidence=min(rewritten.confidence, 0.95),
        )

    @classmethod
    def _detect_task_type(cls, text: str, goal: UserGoal, concerns: list[str]) -> TravelTaskType:
        if any(m in text for m in cls.CROWD_MARKERS):
            return TravelTaskType.CROWD_INQUIRY
        if goal.intent_type == IntentType.COMPARE_PLACES or (
            any(m in text for m in cls.COMPARE_MARKERS) and len(goal.place_candidates) >= 2
        ):
            return TravelTaskType.COMPARE_PLACES
        if goal.intent_type == IntentType.ITINERARY or any(m in text for m in cls.ITINERARY_MARKERS):
            return TravelTaskType.ITINERARY_PLANNING
        if goal.intent_type == IntentType.WEATHER_RISK or any(m in text for m in cls.WEATHER_MARKERS):
            return TravelTaskType.WEATHER_RISK
        if any(m in text for m in cls.FOOD_MARKERS):
            return TravelTaskType.FOOD_NEARBY
        if any(m in text for m in cls.LODGING_MARKERS):
            return TravelTaskType.LODGING_AREA
        if any(m in text for m in cls.TRANSPORT_MARKERS):
            return TravelTaskType.TRANSPORT_PLANNING
        if "elderly_suitability" in concerns or goal.party:
            return TravelTaskType.SINGLE_PLACE_SUITABILITY
        if "crowd_level" in concerns:
            return TravelTaskType.CROWD_INQUIRY
        if goal.place_candidates and goal.intent_type == IntentType.SINGLE_PLACE:
            return TravelTaskType.SINGLE_PLACE_SUITABILITY
        if goal.place_candidates:
            return TravelTaskType.PLACE_FACT_LOOKUP
        return TravelTaskType.OPEN_ENDED_ADVICE

    @classmethod
    def _evidence_for_task(
        cls, task_type: TravelTaskType, concerns: list[str], *, text: str = ""
    ) -> tuple[list[str], list[str]]:
        if task_type == TravelTaskType.CROWD_INQUIRY:
            return ["crowd_level", "queue_time"], ["event", "weather", "reservation_policy"]
        if task_type == TravelTaskType.SINGLE_PLACE_SUITABILITY:
            req = ["walking_intensity", "accessibility", "crowd_level", "transit"]
            opt = ["official_hours", "weather", "nearby_rest_area"]
            if "elderly_suitability" in concerns:
                return req, opt
            return req, opt
        if task_type == TravelTaskType.COMPARE_PLACES:
            return ["crowd_level", "walking_intensity", "transit"], ["official_hours", "ticket_price"]
        if task_type == TravelTaskType.ITINERARY_PLANNING:
            return ["transit", "official_hours", "nearby_food"], ["weather", "lodging_area"]
        if task_type == TravelTaskType.WEATHER_RISK:
            return ["weather"], ["crowd_level", "official_hours"]
        if task_type == TravelTaskType.FOOD_NEARBY:
            needs = infer_all_nearby_needs_from_text(text)
            if not needs or needs == ["nearby_poi"]:
                needs = ["nearby_food"]
            return needs, ["nearby_rest_area"]
        if task_type == TravelTaskType.LODGING_AREA:
            needs = infer_all_nearby_needs_from_text(text)
            lodging = [n for n in needs if n in ("nearby_hotel", "lodging_area")]
            return lodging or ["nearby_hotel"], ["transit"]
        if task_type == TravelTaskType.TRANSPORT_PLANNING:
            return ["transit"], ["walking_intensity"]
        return ["official_hours"], ["reviews", "transit"]

    @classmethod
    async def extract_with_llm(
        cls,
        rewritten: RewrittenQueryResult,
        memory: ConversationMemory,
        goal: UserGoal,
        llm_client,
        place_contexts: list[PlaceContext] | None = None,
    ) -> TravelTask:
        task = cls.extract(rewritten, memory, goal, place_contexts)
        if llm_client._should_use_anthropic():
            try:
                import json

                raw = await llm_client.complete(
                    system='Extract travel task JSON with keys: task_type, key_concerns (list). task_type must be one of crowd_inquiry, single_place_suitability, compare_places, itinerary_planning, weather_risk, place_fact_lookup, open_ended_advice.',
                    user=rewritten.rewritten_query,
                )
                data = json.loads(raw)
                if data.get("task_type"):
                    task.task_type = TravelTaskType(data["task_type"])
                if data.get("key_concerns"):
                    task.key_concerns = list(dict.fromkeys(task.key_concerns + data["key_concerns"]))
            except Exception:
                pass
        return task

    @staticmethod
    def sync_user_goal_intent(task: TravelTask, goal: UserGoal) -> None:
        mapping = {
            TravelTaskType.COMPARE_PLACES: IntentType.COMPARE_PLACES,
            TravelTaskType.ITINERARY_PLANNING: IntentType.ITINERARY,
            TravelTaskType.WEATHER_RISK: IntentType.WEATHER_RISK,
            TravelTaskType.CROWD_INQUIRY: IntentType.SINGLE_PLACE,
            TravelTaskType.SINGLE_PLACE_SUITABILITY: IntentType.SINGLE_PLACE,
            TravelTaskType.PLACE_FACT_LOOKUP: IntentType.SINGLE_PLACE,
            TravelTaskType.FOOD_NEARBY: IntentType.FOOD_LODGING,
            TravelTaskType.LODGING_AREA: IntentType.FOOD_LODGING,
            TravelTaskType.TRANSPORT_PLANNING: IntentType.TRANSPORT,
        }
        goal.intent_type = mapping.get(task.task_type, goal.intent_type)
