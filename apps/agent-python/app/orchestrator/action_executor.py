import logging

from app.agents.query_understanding_agent import QueryUnderstandingAgent
from app.config import get_settings
from app.llm_client import LLMClient
from app.orchestrator.actions import ActionResult, AgentAction, AgentActionType
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.schemas.tool_trace import ToolTrace
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import is_mcp_policy_tool, resolve_tool_name

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Execute validated actions — tools, subagents, clarification."""

    def __init__(self, llm_client=None, tools=None) -> None:
        self.llm = llm_client or LLMClient()
        self.tools = tools
        self._qu_agent = QueryUnderstandingAgent(self.llm)

    async def execute(
        self,
        action: AgentAction,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> ActionResult:
        if action.action_type == AgentActionType.CALL_SUBAGENT:
            return await self._call_subagent(action.target or "", state, action.arguments, prompt_context)
        if action.action_type == AgentActionType.CALL_TOOL:
            return await self._call_tool(action.target or "", action.arguments, state, prompt_context)
        if action.action_type == AgentActionType.ASK_CLARIFICATION:
            return ActionResult(
                output={
                    "needs_clarification": True,
                    "clarification_question": action.arguments.get("question")
                    or "请补充您想查询的具体景点或区域。",
                    "missing_critical_info": action.arguments.get("missing_critical_info", []),
                }
            )
        if action.action_type == AgentActionType.UPDATE_STATE:
            return ActionResult(output={"updates": action.arguments})
        if action.action_type in {AgentActionType.FINISH_STATE, AgentActionType.FAIL_STATE}:
            return ActionResult(output=action.arguments)
        return ActionResult(ok=False, error=f"Unsupported action: {action.action_type.value}")

    async def _call_subagent(
        self,
        name: str,
        state: TravelAgentState,
        arguments: dict,
        prompt_context: dict,
    ) -> ActionResult:
        if name == "query_understanding":
            ctx = state.conversation_context
            if ctx is None:
                return ActionResult(ok=False, error="conversation_context required")
            result = await self._qu_agent.run(
                raw_query=state.raw_user_query,
                conversation_context=ctx,
                supported_regions=prompt_context.get("supported_regions"),
                user_ctx=prompt_context.get("user_ctx"),
            )
            return ActionResult(output={"query_understanding": result})

        if name == "semantic_frame_builder":
            qu = state.query_understanding
            if qu is None:
                qu_data = arguments.get("query_understanding")
                if qu_data is None:
                    return ActionResult(ok=False, error="query_understanding required for semantic_frame_builder")
                from app.schemas.query_understanding import QueryUnderstandingResult

                qu = QueryUnderstandingResult.model_validate(qu_data)
            raw = arguments.get("raw_query", state.raw_user_query)
            frame = SemanticFrameBuilder.build(raw, qu)
            return ActionResult(output={"semantic_frame": frame})

        if name == "place_entity_extractor":
            from app.agents.place_entity_extractor import LLMPlaceEntityExtractor
            from app.catalog.place_resolver import PlaceResolver

            raw = arguments.get("raw_query", state.raw_user_query)
            ctx = state.conversation_context
            extractor = LLMPlaceEntityExtractor(self.llm)
            mentions = await extractor.extract(raw, ctx)
            resolver = PlaceResolver(self.llm, conversation_context=ctx)
            candidates = await resolver.resolve(raw, mentions, ctx)
            return ActionResult(output={"place_candidates": candidates})

        if name == "composer_agent":
            from app.agents.answer_composer_agent import AnswerComposerAgent

            composer = AnswerComposerAgent(self.llm)
            draft = await composer.compose(state, arguments)
            return ActionResult(output={"result": draft})

        if name == "search_task_planner_agent":
            from app.agents.search_task_planner_agent import SearchTaskPlannerAgent

            planner = SearchTaskPlannerAgent(self.llm)
            tasks = await planner.run(state)
            return ActionResult(
                output={
                    "search_tasks": [t.model_dump() for t in tasks],
                    "task_count": len(tasks),
                }
            )

        if name == "keyword_search_agent":
            from app.agents.keyword_search_agent import KeywordSearchAgent

            agent = KeywordSearchAgent(self.tools)
            output = await agent.run(state, arguments, prompt_context)
            loop_state = prompt_context.get("loop_state_name", "evidence_planning_and_tool_use")
            selected_by_llm = bool(prompt_context.get("selected_by_llm", True))
            whitelist_checked = bool(prompt_context.get("tool_whitelist") is not None)
            for trace in output.get("tool_traces", []):
                if isinstance(trace, dict):
                    trace.setdefault("requested_by_state", loop_state)
                    trace.setdefault("selected_by_llm", selected_by_llm)
                    trace.setdefault("whitelist_checked", whitelist_checked)
                    trace["subagent"] = "keyword_search_agent"
            return ActionResult(output=output)

        return ActionResult(ok=False, error=f"Unknown subagent: {name}")

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> ActionResult:
        if not self.tools:
            return ActionResult(ok=False, error="Tool registry unavailable")

        resolved = resolve_tool_name(tool_name)
        payload = self._build_tool_arguments(resolved, arguments, state, prompt_context)
        trace_before = len(self.tools.traces)

        try:
            from app.tool_gateway.integration import try_java_tool_gateway
        except ImportError:
            try_java_tool_gateway = None

        if try_java_tool_gateway is not None:
            gateway_result = await try_java_tool_gateway(
                self, tool_name, resolved, payload, state, prompt_context, trace_before
            )
            if gateway_result is not None:
                return gateway_result

        try:
            evidence = await self.tools.run_tool(resolved, **payload)
            self._annotate_traces(trace_before, tool_name, prompt_context)
            new_traces = self.tools.traces[trace_before:]
            return ActionResult(
                output={
                    "evidence": evidence,
                    "tool_name": resolved,
                    "policy_tool_name": tool_name,
                    "tool_traces": [t.model_dump() for t in new_traces],
                }
            )
        except Exception as exc:
            logger.warning("CALL_TOOL %s failed: %s", resolved, exc)
            self.tools.record_error(resolved, input=payload, error=str(exc))
            self._annotate_traces(trace_before, tool_name, prompt_context)
            new_traces = self.tools.traces[trace_before:]
            return ActionResult(
                ok=False,
                error=str(exc),
                output={
                    "evidence": [],
                    "tool_name": resolved,
                    "policy_tool_name": tool_name,
                    "tool_traces": [t.model_dump() for t in new_traces],
                },
            )

    def _build_tool_arguments(
        self,
        tool_name: str,
        arguments: dict,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> dict:
        args = dict(arguments)
        goal = state.user_goal
        frame = state.semantic_frame
        place_name = (
            args.get("place_name")
            or prompt_context.get("place_name")
            or (frame.entities.places[0] if frame and frame.entities.places else None)
        )
        city = (
            args.get("city")
            or prompt_context.get("city")
            or (goal.destination_city if goal else None)
            or (frame.entities.city if frame else None)
        )
        country = (
            args.get("country")
            or prompt_context.get("country")
            or (goal.destination_country if goal else None)
            or (frame.entities.country if frame else None)
        )

        if tool_name in {"official", "places", "reviews", "transit", "restaurant"} or tool_name.endswith("_mcp"):
            effective_place = place_name or city
            if effective_place and "place_name" not in args:
                args["place_name"] = effective_place
            if country and "country" not in args:
                args["country"] = country
            if city and "city" not in args:
                args["city"] = city
            if goal and goal.start_location and "start_location" not in args:
                args["start_location"] = goal.start_location

        if tool_name in {"weather", "seasonality", "lodging"} or tool_name in {
            "openmeteo_mcp",
            "weather_mcp",
            "climate_mcp",
        }:
            if city and "city" not in args:
                args["city"] = city
            if country and "country" not in args:
                args["country"] = country
            if goal and goal.travel_date and "travel_date" not in args:
                args["travel_date"] = goal.travel_date

        if tool_name == "knowledge_prior":
            args.setdefault("raw_query", state.raw_user_query)
            if frame is not None:
                args.setdefault("semantic_frame", frame)
            args.setdefault("limitations", list(state.limitations))

        if tool_name == "fallback":
            args.setdefault("place_name", place_name or city or "unknown")
            args.setdefault("city", city)
            args.setdefault("country", country)
            args.setdefault("need_types", ["crowd_level"])

        if is_mcp_policy_tool(tool_name):
            if "query" not in args:
                queries = ClaimSearchPlanner.build_queries(state)
                args["query"] = queries[0] if queries else state.raw_user_query
            if frame and frame.information_needs:
                args.setdefault("information_need", frame.information_needs[0])
            need = ClaimSearchPlanner.primary_information_need(state)
            if need:
                args.setdefault("information_need", need)
            settings = get_settings()
            if tool_name in {"browser_mcp", "official_page_reader_mcp", "baidu_place_detail_mcp"}:
                domains = settings.official_page_domain_allowlist() or settings.browser_domain_allowlist()
                if domains:
                    args.setdefault("allowed_domains", domains)
                if state.evidence and "url" not in args and "source_url" not in args:
                    args.setdefault("prior_evidence", list(state.evidence))
                if tool_name == "baidu_place_detail_mcp" and "uid" not in args:
                    from tools.mcp.adapters.baidu_response_parser import pick_baidu_uid_from_evidence

                    uid = pick_baidu_uid_from_evidence(list(state.evidence))
                    if uid:
                        args.setdefault("uid", uid)

        return args

    def _annotate_traces(self, trace_before: int, policy_tool_name: str, prompt_context: dict) -> None:
        if not self.tools or len(self.tools.traces) <= trace_before:
            return

        loop_state = prompt_context.get("loop_state_name", "evidence_planning_and_tool_use")
        selected_by_llm = bool(prompt_context.get("selected_by_llm", True))
        whitelist_checked = bool(prompt_context.get("tool_whitelist") is not None)

        annotated: list[ToolTrace] = []
        for trace in self.tools.traces[trace_before:]:
            annotated.append(
                trace.model_copy(
                    update={
                        "requested_by_state": loop_state,
                        "selected_by_llm": selected_by_llm,
                        "whitelist_checked": whitelist_checked,
                        "tool_name": policy_tool_name if trace.tool_name != policy_tool_name else trace.tool_name,
                    }
                )
            )
        self.tools.traces[trace_before:] = annotated
