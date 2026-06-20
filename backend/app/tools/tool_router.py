from pydantic import BaseModel, Field

from app.schemas.information_need import InformationNeed, InformationNeedType
from app.schemas.travel_task import TravelTask, TravelTaskType
from app.tools.capability_registry import CapabilityRegistry


NEED_TO_CAPABILITY: dict[InformationNeedType, list[str]] = {
    InformationNeedType.OPENING_HOURS: ["opening_hours"],
    InformationNeedType.TICKET_PRICE: ["ticket_price"],
    InformationNeedType.RESERVATION_POLICY: ["reservation_policy"],
    InformationNeedType.TEMPORARY_CLOSURE: ["temporary_closure"],
    InformationNeedType.CROWD_LEVEL: ["crowd_level", "popular_times_proxy"],
    InformationNeedType.QUEUE_TIME: ["queue_time"],
    InformationNeedType.WALKING_INTENSITY: ["walking_intensity", "walking_intensity_proxy"],
    InformationNeedType.ACCESSIBILITY: ["accessibility", "accessibility_proxy"],
    InformationNeedType.WEATHER: ["weather", "weather_risk"],
    InformationNeedType.TRANSIT: ["transit"],
    InformationNeedType.NEARBY_FOOD: ["nearby_food"],
    InformationNeedType.NEARBY_REST_AREA: ["nearby_rest_area", "nearby_poi"],
    InformationNeedType.LOCKER: ["locker"],
    InformationNeedType.STROLLER_FRIENDLINESS: ["stroller_friendliness", "accessibility_proxy"],
    InformationNeedType.PHOTO_SPOT: ["photo_spot"],
    InformationNeedType.SAFETY: ["walking_intensity"],
    InformationNeedType.EVENT: ["event"],
    InformationNeedType.FALLBACK_WEB_LOOKUP: ["fallback_web_lookup"],
}


class ToolExecutionPlan(BaseModel):
    selected_tools: list[str] = Field(default_factory=list)
    need_to_tool_mapping: dict[str, list[str]] = Field(default_factory=dict)
    fallback_used: bool = False
    unsupported_needs: list[str] = Field(default_factory=list)
    routing_explanation: list[str] = Field(default_factory=list)
    estimated_only_needs: list[str] = Field(default_factory=list)
    primary_tool: dict[str, str] = Field(default_factory=dict)
    fallback_tools: dict[str, list[str]] = Field(default_factory=dict)
    selected_reason: dict[str, str] = Field(default_factory=dict)
    requires_api_key: dict[str, bool] = Field(default_factory=dict)
    estimated_only: dict[str, bool] = Field(default_factory=dict)


class ToolRouter:
    LIVE_CROWD_CAPABILITIES = {"live_crowd", "realtime_crowd"}

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self.registry = registry or CapabilityRegistry()

    def available_capabilities(self) -> set[str]:
        """Logical execution tool names available for AnswerModeRouter."""
        caps: set[str] = set()
        for name in self.registry.all_tool_names():
            caps.add(self.registry.execution_tool_name(name))
            if not name.startswith(("real_", "mock_")) and not name.endswith("_mcp"):
                caps.add(name)
        return caps

    def _tools_have_live_crowd(self, tool_names: list[str]) -> bool:
        for tool_name in tool_names:
            for live_cap in self.LIVE_CROWD_CAPABILITIES:
                if self.registry.tool_has_capability(tool_name, live_cap):
                    return True
        return False

    def route(self, needs: list[InformationNeed], task: TravelTask) -> ToolExecutionPlan:
        selected: set[str] = set()
        mapping: dict[str, list[str]] = {}
        unsupported: list[str] = []
        explanations: list[str] = []
        fallback_used = False
        estimated: list[str] = []

        country = task.country
        primary_tool: dict[str, str] = {}
        fallback_tools: dict[str, list[str]] = {}
        selected_reason: dict[str, str] = {}
        requires_api_key: dict[str, bool] = {}
        estimated_only: dict[str, bool] = {}

        for need in needs:
            need_key = need.need_type.value
            caps = NEED_TO_CAPABILITY.get(need.need_type, [need.need_type.value])
            tools_for_need: list[str] = []

            for cap in caps:
                for tool_name, conf in self.registry.tools_for_capability(cap, country):
                    if tool_name == "fallback":
                        continue
                    exec_name = self.registry.execution_tool_name(tool_name)
                    if exec_name not in tools_for_need:
                        tools_for_need.append(exec_name)
                        selected.add(exec_name)
                        if need_key not in primary_tool:
                            primary_tool[need_key] = tool_name
                            selected_reason[need_key] = f"highest confidence {conf:.2f} for {cap}"
                            cap_meta = self.registry.get(tool_name)
                            requires_api_key[need_key] = bool(cap_meta and cap_meta.requires_api_key)
                            p, fallbacks = self.registry.pilot_chain_for_execution_tool(exec_name)
                            if p:
                                primary_tool[need_key] = p
                            if fallbacks:
                                fallback_tools[need_key] = fallbacks

            if need.need_type == InformationNeedType.CROWD_LEVEL:
                has_live_crowd_tool = self._tools_have_live_crowd(tools_for_need)
                if not has_live_crowd_tool:
                    for tool_name, _ in self.registry.tools_for_capability("crowd_level", country):
                        exec_name = self.registry.execution_tool_name(tool_name)
                        if exec_name in {"reviews", "places"} and exec_name not in tools_for_need:
                            tools_for_need.append(exec_name)
                            selected.add(exec_name)
                    if need.fallback_allowed:
                        tools_for_need.append("fallback")
                        selected.add("fallback")
                        fallback_used = True
                        estimated.append(need_key)
                        estimated_only[need_key] = True
                        explanations.append(
                            "crowd_level 无实时人流工具，使用 reviews + places + fallback 估算"
                        )

            if not tools_for_need and need.fallback_allowed:
                tools_for_need = ["fallback"]
                selected.add("fallback")
                fallback_used = True
                explanations.append(f"{need_key} 无直接工具，启用 fallback")
            elif not tools_for_need:
                unsupported.append(need_key)

            mapping[need_key] = tools_for_need

        if task.task_type == TravelTaskType.ITINERARY_PLANNING and "lodging" not in selected:
            selected.add("lodging")
            explanations.append("行程任务补充 lodging 工具")

        if task.task_type == TravelTaskType.LODGING_AREA:
            selected.add("lodging")
            mapping.setdefault("lodging_area", ["lodging"])

        if not selected:
            from app.orchestrator.policies import SourceSelectionPolicy
            from app.schemas.user_query import UserGoal, IntentType

            goal = UserGoal(
                intent_type=IntentType.SINGLE_PLACE,
                destination_country=task.country,
                destination_city=task.city,
                place_candidates=[p.canonical_name for p in task.places],
                travel_date=task.travel_date,
            )
            selected = set(SourceSelectionPolicy.select_tools(goal))
            explanations.append("无信息需求匹配，回退至 SourceSelectionPolicy")

        return ToolExecutionPlan(
            selected_tools=sorted(selected),
            need_to_tool_mapping=mapping,
            fallback_used=fallback_used,
            unsupported_needs=unsupported,
            routing_explanation=explanations,
            estimated_only_needs=estimated,
            primary_tool=primary_tool,
            fallback_tools=fallback_tools,
            selected_reason=selected_reason,
            requires_api_key=requires_api_key,
            estimated_only=estimated_only,
        )
