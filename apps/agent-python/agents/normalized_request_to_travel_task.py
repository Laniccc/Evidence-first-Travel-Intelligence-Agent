from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.place_context import PlaceContext
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.schemas.user_profile import UserProfile
from app.schemas.user_query import UserContext

_PLACE_TYPES = frozenset(
    {"attraction", "landmark", "natural_site", "station", "district"}
)

_TASK_TYPE_MAP: dict[tuple[str, str], TravelTaskType] = {
    ("comparison", "how_to_choose"): TravelTaskType.COMPARE_PLACES,
    ("comparison", "unknown"): TravelTaskType.COMPARE_PLACES,
    ("planning", "route_plan"): TravelTaskType.ITINERARY_PLANNING,
    ("itinerary", "route_plan"): TravelTaskType.ITINERARY_PLANNING,
    ("crowd", "crowd_level"): TravelTaskType.CROWD_INQUIRY,
    ("crowd", "risk_check"): TravelTaskType.CROWD_INQUIRY,
    ("weather", "risk_check"): TravelTaskType.WEATHER_RISK,
    ("weather", "unknown"): TravelTaskType.WEATHER_RISK,
    ("transport", "route_plan"): TravelTaskType.TRANSPORT_PLANNING,
    ("food", "nearby_search"): TravelTaskType.FOOD_NEARBY,
    ("lodging", "nearby_search"): TravelTaskType.LODGING_AREA,
    ("fact_lookup", "opening_hours"): TravelTaskType.PLACE_FACT_LOOKUP,
    ("fact_lookup", "ticket_price"): TravelTaskType.PLACE_FACT_LOOKUP,
    ("suitability", "whether_to_go"): TravelTaskType.SINGLE_PLACE_SUITABILITY,
    ("suitability", "risk_check"): TravelTaskType.SINGLE_PLACE_SUITABILITY,
    ("advisory", "best_time_to_visit"): TravelTaskType.OPEN_ENDED_ADVICE,
    ("advisory", "general_advice"): TravelTaskType.OPEN_ENDED_ADVICE,
    ("advisory", "whether_to_go"): TravelTaskType.OPEN_ENDED_ADVICE,
}


class NormalizedRequestToTravelTask:
    @classmethod
    def convert(cls, req: NormalizedUserRequest, user_ctx: UserContext | None = None) -> TravelTask:
        ctx = user_ctx or UserContext()
        country = next((e.country for e in req.entities if e.country), None)
        city = next((e.city for e in req.entities if e.city), None)
        if not country:
            country = next((e.normalized_name for e in req.entities if e.entity_type == "country"), None)
        if not city:
            city = next((e.normalized_name for e in req.entities if e.entity_type == "city"), None)

        places = [
            PlaceContext(
                original_name=e.text,
                canonical_name=e.normalized_name or e.text,
                country=e.country or country,
                city=e.city or city,
                confidence=e.confidence,
                source=e.source,
            )
            for e in req.entities
            if e.entity_type in _PLACE_TYPES
        ]

        task_type = _TASK_TYPE_MAP.get(
            (req.task_family, req.decision_type),
            TravelTaskType.OPEN_ENDED_ADVICE,
        )
        if places and task_type == TravelTaskType.OPEN_ENDED_ADVICE and req.decision_type == "opening_hours":
            task_type = TravelTaskType.PLACE_FACT_LOOKUP
        if places and req.decision_type == "crowd_level":
            task_type = TravelTaskType.CROWD_INQUIRY

        required, optional = cls._evidence_for(task_type, req)
        profile = UserProfile(
            party=list(req.user_constraints.party),
            pace=req.user_constraints.pace,
            preferences=list(req.user_constraints.preferences),
            budget_level=req.user_constraints.budget,
        )

        return TravelTask(
            task_type=task_type,
            rewritten_query=req.rewritten_query,
            country=country,
            city=city,
            places=places,
            travel_date=ctx.travel_date,
            start_location=ctx.start_location,
            user_profile=profile,
            key_concerns=[n.need_type for n in req.information_needs],
            required_evidence=required,
            optional_evidence=optional,
            constraints=list(req.user_constraints.constraints),
            assumptions=[],
            confidence=req.confidence,
        )

    @staticmethod
    def _evidence_for(task_type: TravelTaskType, req: NormalizedUserRequest) -> tuple[list[str], list[str]]:
        needs = [n.need_type for n in req.information_needs]
        if needs:
            return needs[:3], needs[3:] or ["reviews"]
        mapping = {
            TravelTaskType.CROWD_INQUIRY: (["crowd_level", "queue_time"], ["event"]),
            TravelTaskType.PLACE_FACT_LOOKUP: (["official_hours"], ["weather"]),
            TravelTaskType.SINGLE_PLACE_SUITABILITY: (["walking_intensity", "crowd_level"], ["official_hours"]),
            TravelTaskType.COMPARE_PLACES: (["crowd_level", "transit"], ["official_hours"]),
            TravelTaskType.ITINERARY_PLANNING: (["transit", "official_hours"], ["weather"]),
            TravelTaskType.WEATHER_RISK: (["weather"], ["official_hours"]),
            TravelTaskType.OPEN_ENDED_ADVICE: (["seasonality", "best_time_to_visit"], ["weather"]),
        }
        return mapping.get(task_type, (["official_hours"], ["transit"]))
