from app.schemas.evidence import ClaimType, Evidence
from app.schemas.user_query import QueryPlan, UserGoal
from app.tools import ToolRegistry


class PlaceResearchAgent:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    async def retrieve_for_place(self, place_name: str, goal: UserGoal) -> list[Evidence]:
        evidence: list[Evidence] = []
        for tool in [
            self.tools.official,
            self.tools.places,
            self.tools.transit,
            self.tools.reviews,
            self.tools.restaurant,
        ]:
            batch = await tool.run(place_name=place_name, start_location=goal.start_location)
            evidence.extend(batch)
        if goal.destination_city and goal.destination_country:
            evidence.extend(
                await self.tools.weather.run(
                    city=goal.destination_city,
                    country=goal.destination_country,
                    travel_date=goal.travel_date,
                )
            )
        return evidence

    @staticmethod
    def build_query_plan(goal: UserGoal) -> QueryPlan:
        required = ["official_hours", "ticket_policy", "address", "transit", "recent_reviews"]
        if goal.travel_date:
            required.append("weather")
        if goal.party:
            required.extend(["walking_intensity", "crowd", "accessibility"])
        if goal.intent_type.value == "itinerary":
            required.extend(["nearby_food", "transit_order"])
        return QueryPlan(required_info=required, optional_info=["nearby_lodging_area", "reservation_policy"])
