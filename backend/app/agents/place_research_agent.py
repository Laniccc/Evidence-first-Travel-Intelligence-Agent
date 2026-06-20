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
        limitations: list[str] | None = None,
    ) -> list[Evidence]:
        selected = tool_names or (tool_plan.selected_tools if tool_plan else None) or SourceSelectionPolicy.select_tools(goal)
        effective = self._effective_goal(goal, place_context)
        crowd_needs = tool_plan.estimated_only_needs if tool_plan else []
        query_context = effective.constraints[0] if effective.constraints else place_name

        evidence: list[Evidence] = []
        for tool_name in selected:
            batch = await self._invoke_tool(
                tool_name=tool_name,
                place_name=place_name,
                goal=effective,
                crowd_needs=crowd_needs,
                query_context=query_context,
                limitations=limitations,
            )
            evidence.extend(batch)
        return evidence

    async def _invoke_tool(
        self,
        tool_name: str,
        place_name: str,
        goal: UserGoal,
        crowd_needs: list[str],
        query_context: str,
        limitations: list[str] | None,
    ) -> list[Evidence]:
        if tool_name == "weather":
            return await self._run_weather(goal, limitations)
        if tool_name == "lodging":
            return await self._run_lodging(goal, limitations)
        if tool_name == "fallback":
            return await self._run_fallback(
                place_name=place_name,
                goal=goal,
                crowd_needs=crowd_needs,
                query_context=query_context,
                limitations=limitations,
            )
        return await self.tools.run_tool(
            tool_name,
            place_name=place_name,
            start_location=goal.start_location,
        )

    async def _run_weather(self, goal: UserGoal, limitations: list[str] | None) -> list[Evidence]:
        if not (goal.destination_city and goal.destination_country):
            if limitations is not None:
                limitations.append("天气查询缺少 destination city/country，已记录 error trace。")
            self.tools.record_skipped_tool(
                "weather",
                "missing destination_city or destination_country",
                city=goal.destination_city,
                country=goal.destination_country,
                travel_date=goal.travel_date,
            )
            return []
        return await self.tools.run_tool(
            "weather",
            city=goal.destination_city,
            country=goal.destination_country,
            travel_date=goal.travel_date,
        )

    async def _run_lodging(self, goal: UserGoal, limitations: list[str] | None) -> list[Evidence]:
        if not (goal.destination_city and goal.destination_country):
            if limitations is not None:
                limitations.append("住宿区域查询缺少 destination city/country，已记录 error trace。")
            self.tools.record_skipped_tool(
                "lodging",
                "missing destination_city or destination_country",
                city=goal.destination_city,
                country=goal.destination_country,
            )
            return []
        return await self.tools.run_tool(
            "lodging",
            city=goal.destination_city,
            country=goal.destination_country,
        )

    async def _run_fallback(
        self,
        place_name: str,
        goal: UserGoal,
        crowd_needs: list[str],
        query_context: str,
        limitations: list[str] | None,
    ) -> list[Evidence]:
        if not (goal.destination_city and goal.destination_country):
            if limitations is not None:
                limitations.append("fallback 缺少 destination city/country，已记录 error trace。")
            self.tools.record_skipped_tool(
                "fallback",
                "missing destination_city or destination_country",
                place_name=place_name,
                country=goal.destination_country,
                city=goal.destination_city,
                need_types=crowd_needs or ["crowd_level"],
                query_context=query_context,
            )
            return []
        return await self.tools.run_tool(
            "fallback",
            place_name=place_name,
            country=goal.destination_country,
            city=goal.destination_city,
            need_types=crowd_needs or ["crowd_level"],
            query_context=query_context,
        )

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
