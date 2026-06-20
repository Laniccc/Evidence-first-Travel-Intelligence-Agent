from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_profile import UserProfile
from app.schemas.user_query import (
    BudgetLevel,
    IntentType,
    PaceType,
    PartyType,
    TransportPreference,
    UserContext,
    UserGoal,
)

SUPPORTED_REGIONS = {"Japan", "China", "South Korea"}
LOW_CONFIDENCE_THRESHOLD = 0.35


class TravelTaskToUserGoalAdapter:
    TASK_INTENT_MAP: dict[TravelTaskType, IntentType] = {
        TravelTaskType.SINGLE_PLACE_SUITABILITY: IntentType.SINGLE_PLACE,
        TravelTaskType.PLACE_FACT_LOOKUP: IntentType.SINGLE_PLACE,
        TravelTaskType.CROWD_INQUIRY: IntentType.SINGLE_PLACE,
        TravelTaskType.WEATHER_RISK: IntentType.WEATHER_RISK,
        TravelTaskType.COMPARE_PLACES: IntentType.COMPARE_PLACES,
        TravelTaskType.ITINERARY_PLANNING: IntentType.ITINERARY,
        TravelTaskType.FOOD_NEARBY: IntentType.FOOD_LODGING,
        TravelTaskType.LODGING_AREA: IntentType.FOOD_LODGING,
        TravelTaskType.TRANSPORT_PLANNING: IntentType.TRANSPORT,
        TravelTaskType.OPEN_ENDED_ADVICE: IntentType.GENERAL,
    }

    @classmethod
    def to_user_goal(cls, task: TravelTask, user_ctx: UserContext | None = None) -> UserGoal:
        ctx = user_ctx or UserContext()
        profile = task.user_profile or UserProfile()

        party = cls._merge_party(profile, ctx)
        pace = cls._merge_pace(profile, ctx)
        budget = cls._merge_budget(profile, ctx)
        transport = cls._merge_transport(profile, ctx)

        place_candidates = [p.canonical_name or p.original_name for p in task.places if (p.canonical_name or p.original_name)]

        preferences = list(dict.fromkeys((profile.preferences or []) + (ctx.preferences or [])))
        constraints = list(dict.fromkeys((profile.constraints or []) + (ctx.constraints or []) + task.constraints))

        return UserGoal(
            intent_type=cls.TASK_INTENT_MAP.get(task.task_type, IntentType.GENERAL),
            destination_country=task.country,
            destination_city=task.city,
            place_candidates=place_candidates,
            travel_date=task.travel_date or ctx.travel_date,
            start_location=task.start_location or ctx.start_location,
            party=party,
            budget_level=budget,
            pace=pace,
            transport_preference=transport,
            preferences=preferences,
            constraints=constraints,
        )

    @staticmethod
    def _merge_party(profile: UserProfile, ctx: UserContext) -> list[PartyType]:
        party: list[PartyType] = []
        for raw in profile.party:
            try:
                pt = PartyType(raw)
                if pt not in party:
                    party.append(pt)
            except ValueError:
                continue
        for pt in ctx.party:
            if pt not in party:
                party.append(pt)
        return party

    @staticmethod
    def _merge_pace(profile: UserProfile, ctx: UserContext) -> PaceType:
        if ctx.pace != PaceType.UNKNOWN:
            return ctx.pace
        if profile.pace:
            try:
                return PaceType(profile.pace)
            except ValueError:
                pass
        return PaceType.UNKNOWN

    @staticmethod
    def _merge_budget(profile: UserProfile, ctx: UserContext) -> BudgetLevel:
        if ctx.budget_level != BudgetLevel.UNKNOWN:
            return ctx.budget_level
        if profile.budget_level:
            try:
                return BudgetLevel(profile.budget_level)
            except ValueError:
                pass
        return BudgetLevel.UNKNOWN

    @staticmethod
    def _merge_transport(profile: UserProfile, ctx: UserContext) -> TransportPreference:
        if ctx.transport_preference != TransportPreference.UNKNOWN:
            return ctx.transport_preference
        if profile.transport_preference:
            try:
                return TransportPreference(profile.transport_preference)
            except ValueError:
                pass
        return TransportPreference.UNKNOWN

    @staticmethod
    def can_generate_user_goal(task: TravelTask) -> bool:
        if task.places or task.country:
            return True
        if task.city and task.task_type == TravelTaskType.ITINERARY_PLANNING:
            return True
        return False

    @classmethod
    def should_use_task(
        cls,
        task: TravelTask | None,
        query_understanding: QueryUnderstandingResult | None,
        confidence: float,
    ) -> bool:
        """Use TravelTask adapter unless QU missing, task missing, or confidence is very low with no mappable goal."""
        if query_understanding is None or task is None:
            return False
        if cls.can_generate_user_goal(task):
            return True
        return confidence >= LOW_CONFIDENCE_THRESHOLD

    @staticmethod
    def has_usable_task(task: TravelTask | None, confidence: float) -> bool:
        """Backward-compatible helper; prefer should_use_task with query_understanding."""
        if not task:
            return False
        if TravelTaskToUserGoalAdapter.can_generate_user_goal(task):
            return True
        return confidence >= LOW_CONFIDENCE_THRESHOLD
