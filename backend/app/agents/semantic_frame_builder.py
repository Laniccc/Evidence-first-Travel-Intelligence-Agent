import re

from app.catalog.location_resolver import resolve_city_country_from_text
from app.catalog.place_catalog import get_place_catalog
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)
from app.schemas.travel_task import TravelTaskType


# Structural patterns for decision_type — not answer templates.
_BEST_TIME_PATTERN = re.compile(r"(几月|什么时候|何时|最佳.*时间|适合.*(去|玩|旅游))", re.I)
_OPENING_HOURS_PATTERN = re.compile(r"(几点|关门|营业|开放时间|开馆|闭馆)", re.I)
_TODAY_PATTERN = re.compile(r"(今天|今日|现在|currently|today|right now)", re.I)
_CROWD_PATTERN = re.compile(r"(人流|人多|拥挤|排队|crowd|busy)", re.I)


class SemanticFrameBuilder:
    """Derive SemanticFrame from query understanding output — primary routing input."""

    @classmethod
    def build(cls, raw_query: str, qu: QueryUnderstandingResult) -> SemanticFrame:
        task = qu.travel_task
        catalog = get_place_catalog()
        text = raw_query.strip()
        places = [p.canonical_name for p in task.places] if task.places else catalog.find_places_in_text(text)

        country = task.country
        city = task.city
        if not city or not country:
            resolved = resolve_city_country_from_text(text)
            if resolved:
                country, city = resolved

        entities = SemanticEntities(country=country, city=city, places=places)
        decision_type = cls._infer_decision_type(text, places, qu)
        query_scope = cls._infer_query_scope(places, city, country, task.task_type)
        time_scope = cls._infer_time_scope(text, decision_type)
        information_needs = cls._infer_information_needs(decision_type, text, task.key_concerns)
        requires_live = cls._requires_live_data(text, information_needs, time_scope)
        requires_exact = cls._requires_exact_fact(decision_type, information_needs, query_scope)
        can_prior = cls._can_use_model_prior(decision_type, information_needs, requires_exact, requires_live)
        missing = list(qu.missing_critical_info)

        if qu.needs_clarification:
            missing.extend(qu.missing_critical_info or ["clarification"])

        frame = SemanticFrame(
            raw_query=text,
            normalized_request=qu.rewritten_query or text,
            query_scope=query_scope,
            task_family=cls._infer_task_family(task.task_type, decision_type),
            decision_type=decision_type,
            entities=entities,
            time_scope=time_scope,
            user_constraints=list(task.constraints),
            key_concerns=list(qu.key_concerns or task.key_concerns),
            information_needs=information_needs,
            missing_slots=missing,
            confidence=qu.confidence,
            requires_live_data=requires_live,
            requires_exact_fact=requires_exact,
            can_answer_with_model_prior=can_prior,
            needs_clarification=qu.needs_clarification,
        )
        return frame

    @classmethod
    def build_city_best_time(
        cls,
        raw_query: str,
        country: str,
        city: str,
        rewritten_query: str,
        confidence: float,
    ) -> SemanticFrame:
        """Explicit SemanticFrame for city-level best-time questions (e.g. 札幌适合几月份去？)."""
        return SemanticFrame(
            raw_query=raw_query.strip(),
            normalized_request=rewritten_query,
            query_scope=QueryScope.CITY,
            task_family=TaskFamily.ADVISORY,
            decision_type=DecisionType.BEST_TIME_TO_VISIT,
            entities=SemanticEntities(country=country, city=city, places=[]),
            time_scope=TimeScope.SEASONAL,
            key_concerns=["seasonality"],
            information_needs=["best_time_to_visit", "seasonality"],
            confidence=confidence,
            requires_live_data=False,
            requires_exact_fact=False,
            can_answer_with_model_prior=True,
            needs_clarification=False,
        )

    @classmethod
    def attach(cls, raw_query: str, qu: QueryUnderstandingResult) -> SemanticFrame:
        if qu.semantic_frame is not None:
            return qu.semantic_frame
        frame = cls.build(raw_query, qu)
        qu.semantic_frame = frame
        return frame

    @classmethod
    def _infer_decision_type(cls, text: str, places: list[str], qu: QueryUnderstandingResult) -> DecisionType:
        if _OPENING_HOURS_PATTERN.search(text) and places:
            return DecisionType.FACT_LOOKUP
        if _BEST_TIME_PATTERN.search(text) and not _OPENING_HOURS_PATTERN.search(text):
            return DecisionType.BEST_TIME_TO_VISIT
        if _CROWD_PATTERN.search(text):
            return DecisionType.RISK_CHECK
        if qu.travel_task.task_type == TravelTaskType.COMPARE_PLACES:
            return DecisionType.HOW_TO_CHOOSE
        if qu.travel_task.task_type == TravelTaskType.ITINERARY_PLANNING:
            return DecisionType.ROUTE_PLAN
        if qu.travel_task.task_type == TravelTaskType.OPEN_ENDED_ADVICE:
            return DecisionType.GENERAL_ADVICE
        if places:
            return DecisionType.WHETHER_TO_GO
        return DecisionType.UNKNOWN

    @classmethod
    def _infer_query_scope(
        cls,
        places: list[str],
        city: str | None,
        country: str | None,
        task_type: TravelTaskType,
    ) -> QueryScope:
        if task_type == TravelTaskType.ITINERARY_PLANNING:
            return QueryScope.ITINERARY
        if places:
            return QueryScope.PLACE
        if city:
            return QueryScope.CITY
        if country:
            return QueryScope.COUNTRY
        return QueryScope.UNKNOWN

    @classmethod
    def _infer_time_scope(cls, text: str, decision_type: DecisionType) -> TimeScope:
        if _TODAY_PATTERN.search(text):
            return TimeScope.CURRENT
        if decision_type == DecisionType.BEST_TIME_TO_VISIT:
            return TimeScope.SEASONAL
        if re.search(r"\d{4}-\d{2}-\d{2}|明天|后天", text):
            return TimeScope.SPECIFIC_DATE
        if re.search(r"\d{1,2}月", text):
            return TimeScope.MONTH
        return TimeScope.UNKNOWN

    @classmethod
    def _infer_information_needs(
        cls,
        decision_type: DecisionType,
        text: str,
        concerns: list[str],
    ) -> list[str]:
        needs: list[str] = []
        if decision_type == DecisionType.BEST_TIME_TO_VISIT:
            needs.extend(["best_time_to_visit", "seasonality"])
        if decision_type == DecisionType.FACT_LOOKUP and _OPENING_HOURS_PATTERN.search(text):
            needs.append("opening_hours")
        if _TODAY_PATTERN.search(text) and re.search(r"天气|weather|下雨|rain", text, re.I):
            needs.append("weather_today")
        elif "weather" in concerns:
            needs.append("weather")
        if _CROWD_PATTERN.search(text) or "crowd_level" in concerns:
            needs.append("current_crowd" if _TODAY_PATTERN.search(text) else "crowd_level")
        if decision_type == DecisionType.GENERAL_ADVICE:
            needs.append("general_travel_advice")
        for c in concerns:
            if c not in needs and c not in {"elderly_suitability", "value_for_money"}:
                needs.append(c)
        return list(dict.fromkeys(needs))

    @classmethod
    def _requires_live_data(cls, text: str, needs: list[str], time_scope: TimeScope) -> bool:
        if time_scope == TimeScope.CURRENT:
            return True
        return any(n in {"weather_today", "current_crowd", "opening_hours"} for n in needs) and _TODAY_PATTERN.search(
            text
        )

    @classmethod
    def _requires_exact_fact(
        cls,
        decision_type: DecisionType,
        needs: list[str],
        scope: QueryScope,
    ) -> bool:
        if decision_type == DecisionType.FACT_LOOKUP:
            return True
        if scope == QueryScope.PLACE and any(n in {"opening_hours", "ticket_price", "reservation_policy"} for n in needs):
            return True
        if "weather_today" in needs:
            return True
        return False

    @classmethod
    def _can_use_model_prior(
        cls,
        decision_type: DecisionType,
        needs: list[str],
        requires_exact: bool,
        requires_live: bool,
    ) -> bool:
        if requires_exact or requires_live:
            return False
        if decision_type in {DecisionType.BEST_TIME_TO_VISIT, DecisionType.GENERAL_ADVICE}:
            return True
        return all(
            need in {"best_time_to_visit", "seasonality", "general_travel_advice"} for need in needs
        ) if needs else False

    @classmethod
    def _infer_task_family(cls, task_type: TravelTaskType, decision_type: DecisionType) -> TaskFamily:
        mapping = {
            TravelTaskType.CROWD_INQUIRY: TaskFamily.CROWD,
            TravelTaskType.COMPARE_PLACES: TaskFamily.COMPARISON,
            TravelTaskType.ITINERARY_PLANNING: TaskFamily.PLANNING,
            TravelTaskType.WEATHER_RISK: TaskFamily.WEATHER,
            TravelTaskType.SINGLE_PLACE_SUITABILITY: TaskFamily.SUITABILITY,
            TravelTaskType.PLACE_FACT_LOOKUP: TaskFamily.FACT_LOOKUP,
            TravelTaskType.OPEN_ENDED_ADVICE: TaskFamily.ADVISORY,
        }
        if decision_type == DecisionType.BEST_TIME_TO_VISIT:
            return TaskFamily.ADVISORY
        return mapping.get(task_type, TaskFamily.UNKNOWN)
