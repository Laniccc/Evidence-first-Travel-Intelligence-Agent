from app.orchestrator.policies import SourceSelectionPolicy
from app.schemas.evidence import Evidence
from app.schemas.place_context import PlaceContext
from app.schemas.user_query import QueryPlan, UserGoal
from app.tools.registry import ToolRegistry
from app.tools.tool_router import ToolExecutionPlan


class PlaceResearchAgent:
    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    def _effective_goal(self, goal: UserGoal, place_context: PlaceContext | None) -> UserGoal:
        if not place_context or not (place_context.country and place_context.city):
            return goal
        return goal.model_copy(
            update={
                "destination_country": place_context.country,
                "destination_city": place_context.city,
            }
        )

    async def retrieve_for_place(
        self,
        place_name: str,
        goal: UserGoal,
        tool_names: list[str] | None = None,
        place_context: PlaceContext | None = None,
        tool_plan: ToolExecutionPlan | None = None,
    ) -> list[Evidence]:
        selected = tool_names or (tool_plan.selected_tools if tool_plan else None) or SourceSelectionPolicy.select_tools(goal)
        effective = self._effective_goal(goal, place_context)
        evidence: list[Evidence] = []
        crowd_needs = []
        if tool_plan:
            crowd_needs = tool_plan.estimated_only_needs

        for tool_name in selected:
            if tool_name == "weather":
                if effective.destination_city and effective.destination_country:
                    evidence.extend(
                        await self.tools.run_tool(
                            "weather",
                            city=effective.destination_city,
                            country=effective.destination_country,
                            travel_date=effective.travel_date,
                        )
                    )
                continue
            if tool_name == "lodging":
                if effective.destination_city and effective.destination_country:
                    evidence.extend(
                        await self.tools.run_tool(
                            "lodging",
                            city=effective.destination_city,
                            country=effective.destination_country,
                        )
                    )
                continue
            if tool_name == "fallback":
                evidence.extend(
                    await self.tools.run_tool(
                        "fallback",
                        place_name=place_name,
                        country=effective.destination_country or "Japan",
                        city=effective.destination_city or "Kyoto",
                        need_types=crowd_needs or ["crowd_level"],
                    )
                )
                continue
            evidence.extend(
                await self.tools.run_tool(
                    tool_name,
                    place_name=place_name,
                    start_location=effective.start_location,
                )
            )
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
