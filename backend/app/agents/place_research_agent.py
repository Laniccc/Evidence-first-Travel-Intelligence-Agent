from app.orchestrator.policies import SourceSelectionPolicy
from app.schemas.evidence import Evidence
from app.schemas.user_query import QueryPlan, UserGoal
from app.tools import ToolRegistry


class PlaceResearchAgent:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    async def retrieve_for_place(
        self,
        place_name: str,
        goal: UserGoal,
        tool_names: list[str] | None = None,
    ) -> list[Evidence]:
        selected = tool_names or SourceSelectionPolicy.select_tools(goal)
        evidence: list[Evidence] = []

        for tool_name in selected:
            if tool_name == "weather":
                if goal.destination_city and goal.destination_country:
                    evidence.extend(
                        await self.tools.weather.run(
                            city=goal.destination_city,
                            country=goal.destination_country,
                            travel_date=goal.travel_date,
                        )
                    )
                continue
            if tool_name == "lodging":
                if goal.destination_city and goal.destination_country:
                    evidence.extend(
                        await self.tools.lodging.run(
                            city=goal.destination_city,
                            country=goal.destination_country,
                        )
                    )
                continue

            tool = getattr(self.tools, tool_name, None)
            if tool is None:
                continue
            batch = await tool.run(place_name=place_name, start_location=goal.start_location)
            evidence.extend(batch)

        return evidence

    @staticmethod
    def build_query_plan(goal: UserGoal) -> QueryPlan:
        tools = SourceSelectionPolicy.select_tools(goal)
        required = ["official_hours", "ticket_policy", "address", "transit", "recent_reviews"]
        if "weather" in tools:
            required.append("weather")
        if goal.party:
            required.extend(["walking_intensity", "crowd", "accessibility"])
        if goal.intent_type.value == "itinerary":
            required.extend(["nearby_food", "transit_order"])
        return QueryPlan(
            required_info=required,
            optional_info=["nearby_lodging_area", "reservation_policy"],
            missing_but_acceptable=[t for t in ["lodging"] if t in tools],
        )
