from app.agents.query_understanding_agent import QueryUnderstandingAgent
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.catalog.place_resolver import resolve_places_for_query
from app.llm_client import LLMClient
from app.orchestrator.actions import ActionResult, AgentAction, AgentActionType
from app.schemas.user_query import TravelAgentState


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
            return await self._call_tool(action.target or "", action.arguments)
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
            place_candidates = await resolve_places_for_query(
                state.raw_user_query, ctx, self.llm
            )
            result = await self._qu_agent.run(
                raw_query=state.raw_user_query,
                conversation_context=ctx,
                supported_regions=prompt_context.get("supported_regions"),
                user_ctx=prompt_context.get("user_ctx"),
            )
            result = SemanticFrameBuilder.ensure_result(
                state.raw_user_query, result, place_candidates
            )
            return ActionResult(output={"query_understanding": result, "place_candidates": place_candidates})

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

        return ActionResult(ok=False, error=f"Unknown subagent: {name}")

    async def _call_tool(self, tool_name: str, arguments: dict) -> ActionResult:
        if not self.tools:
            return ActionResult(ok=False, error="Tool registry unavailable")
        evidence = await self.tools.run_tool(tool_name, **arguments)
        return ActionResult(output={"evidence": evidence, "tool_name": tool_name})
