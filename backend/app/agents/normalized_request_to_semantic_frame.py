from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.semantic_frame import (
    DecisionType,
    QueryScope,
    SemanticEntities,
    SemanticFrame,
    TaskFamily,
    TimeScope,
)


_SCOPE_MAP = {
    "place": QueryScope.PLACE,
    "city": QueryScope.CITY,
    "region": QueryScope.REGION,
    "country": QueryScope.COUNTRY,
    "route": QueryScope.REGION,
    "itinerary": QueryScope.ITINERARY,
    "unknown": QueryScope.UNKNOWN,
}

_FAMILY_MAP = {
    "fact_lookup": TaskFamily.FACT_LOOKUP,
    "suitability": TaskFamily.SUITABILITY,
    "comparison": TaskFamily.COMPARISON,
    "planning": TaskFamily.PLANNING,
    "advisory": TaskFamily.ADVISORY,
    "crowd": TaskFamily.CROWD,
    "weather": TaskFamily.WEATHER,
    "transport": TaskFamily.TRANSPORT,
    "food": TaskFamily.FOOD,
    "lodging": TaskFamily.LODGING,
    "unknown": TaskFamily.UNKNOWN,
}

_DECISION_MAP = {
    "best_time_to_visit": DecisionType.BEST_TIME_TO_VISIT,
    "whether_to_go": DecisionType.WHETHER_TO_GO,
    "how_to_choose": DecisionType.HOW_TO_CHOOSE,
    "risk_check": DecisionType.RISK_CHECK,
    "route_plan": DecisionType.ROUTE_PLAN,
    "nearby_search": DecisionType.NEARBY_SEARCH,
    "opening_hours": DecisionType.FACT_LOOKUP,
    "ticket_price": DecisionType.FACT_LOOKUP,
    "crowd_level": DecisionType.RISK_CHECK,
    "general_advice": DecisionType.GENERAL_ADVICE,
    "unknown": DecisionType.UNKNOWN,
}

_TIME_MAP = {
    "current": TimeScope.CURRENT,
    "specific_date": TimeScope.SPECIFIC_DATE,
    "month": TimeScope.MONTH,
    "seasonal": TimeScope.SEASONAL,
    "flexible": TimeScope.FLEXIBLE,
    "unknown": TimeScope.UNKNOWN,
}

_PLACE_TYPES = frozenset(
    {"attraction", "landmark", "natural_site", "station", "district"}
)


class NormalizedRequestToSemanticFrame:
    """Strict 1:1 mapping — S2 prompt must emit S3-ready fields; no inference here."""

    @classmethod
    def convert(cls, req: NormalizedUserRequest) -> SemanticFrame:
        country = next((e.country for e in req.entities if e.country), None)
        city = next((e.city for e in req.entities if e.city), None)
        region = next((e.region or e.normalized_name for e in req.entities if e.entity_type == "region"), None)
        places = [
            e.normalized_name or e.text
            for e in req.entities
            if e.entity_type in _PLACE_TYPES
        ]

        if not country:
            country = next((e.normalized_name for e in req.entities if e.entity_type == "country"), None)
        if not city:
            city = next((e.normalized_name for e in req.entities if e.entity_type == "city"), None)

        info_needs = [n.need_type for n in req.information_needs]
        key_concerns = list(dict.fromkeys(info_needs + req.user_constraints.constraints))

        return SemanticFrame(
            raw_query=req.raw_query,
            normalized_request=req.rewritten_query,
            query_scope=_SCOPE_MAP.get(req.query_scope, QueryScope.UNKNOWN),
            task_family=_FAMILY_MAP.get(req.task_family, TaskFamily.UNKNOWN),
            decision_type=_DECISION_MAP.get(req.decision_type, DecisionType.UNKNOWN),
            entities=SemanticEntities(country=country, city=city, places=places, region=region),
            time_scope=_TIME_MAP.get(req.time_scope.scope, TimeScope.UNKNOWN),
            user_constraints=list(req.user_constraints.constraints),
            key_concerns=key_concerns,
            information_needs=info_needs,
            missing_slots=list(req.missing_critical_info),
            confidence=req.confidence,
            requires_live_data=req.answer_policy.requires_live_data,
            requires_exact_fact=req.answer_policy.requires_exact_fact,
            can_answer_with_model_prior=req.answer_policy.can_answer_with_model_prior,
            needs_clarification=req.needs_clarification,
        )
