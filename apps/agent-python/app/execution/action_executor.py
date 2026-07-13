import logging
import importlib
from typing import Any

from app.tools.tool_name_resolver import resolve_tool_name

from .actions import ActionResult, AgentAction, AgentActionType
from .entity_resolution import EntityResolutionAgent

logger = logging.getLogger(__name__)


def _module(name: str):
    return importlib.import_module(name)


def _llm_client_class():
    return _module("app.llm_client").LLMClient


def _query_understanding_agent_class():
    return _module("app.understanding.query_understanding_agent").QueryUnderstandingAgent


def _execution_agent_class(module_name: str, class_name: str):
    return getattr(_module("app.execution." + module_name), class_name)


class ActionExecutor:
    """Execute validated actions — tools, subagents, clarification."""

    def __init__(self, llm_client=None, tools=None) -> None:
        self.llm = llm_client or _llm_client_class()()
        self.tools = tools
        self._qu_agent = _query_understanding_agent_class()(self.llm)

    async def execute(
        self,
        action: AgentAction,
        state: Any,
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
        state: Any,
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
                QueryUnderstandingResult = _module(
                    "app.understanding.query_understanding_model"
                ).QueryUnderstandingResult
                qu = QueryUnderstandingResult.model_validate(qu_data)
            raw = arguments.get("raw_query", state.raw_user_query)
            frame = SemanticFrameBuilder.build(raw, qu)
            return ActionResult(output={"semantic_frame": frame})

        if name == "place_entity_extractor":
            raw = arguments.get("raw_query", state.raw_user_query)
            ctx = state.conversation_context
            LLMPlaceEntityExtractor = _module(
                "app.understanding.place_entity_extractor"
            ).LLMPlaceEntityExtractor
            PlaceResolver = _module("app.integrations.places.place_resolver").PlaceResolver
            extractor = LLMPlaceEntityExtractor(self.llm)
            mentions = await extractor.extract(raw, ctx)
            resolver = PlaceResolver(self.llm, conversation_context=ctx)
            candidates = await resolver.resolve(raw, mentions, ctx)
            return ActionResult(output={"place_candidates": candidates})

        if name == "composer_agent":
            AnswerComposerAgent = _module("app.composition.answer_composer").AnswerComposerAgent
            composer = AnswerComposerAgent(self.llm)
            draft = await composer.compose(state, arguments)
            return ActionResult(output={"result": draft})

        if name == "evidence_curation_planner_agent":
            EvidenceCurationPlannerAgent = _module(
                "app.evidence.evidence_curation_planner_agent"
            ).EvidenceCurationPlannerAgent
            agent = EvidenceCurationPlannerAgent(self.llm)
            output = await agent.run(state, arguments)
            return ActionResult(output=output)

        if name == "claim_relevance_filter_agent":
            ClaimRelevanceFilterAgent = _module(
                "app.evidence.claim_relevance_filter_agent"
            ).ClaimRelevanceFilterAgent
            agent = ClaimRelevanceFilterAgent(self.llm)
            output = await agent.run(state, arguments)
            return ActionResult(output=output)

        if name == "evidence_conflict_analyzer_agent":
            EvidenceConflictAnalyzerAgent = _module(
                "app.evidence.evidence_conflict_analyzer_agent"
            ).EvidenceConflictAnalyzerAgent
            agent = EvidenceConflictAnalyzerAgent(self.llm)
            output = await agent.run(state, arguments)
            return ActionResult(output=output)

        if name == "search_task_planner_agent":
            SearchTaskPlannerAgent = _module("app.planning.search_task_planner_agent").SearchTaskPlannerAgent
            refine = bool((arguments or {}).get("refine"))
            planner = SearchTaskPlannerAgent(self.llm)
            tasks = await planner.run(state, refine=refine)
            return ActionResult(
                output={
                    "search_tasks": [t.model_dump() for t in tasks],
                    "task_count": len(tasks),
                    "refine": refine,
                }
            )

        if name == "evidence_contradiction_decomposer_agent":
            EvidenceContradictionDecomposerAgent = _module(
                "app.evidence.evidence_contradiction_decomposer_agent"
            ).EvidenceContradictionDecomposerAgent
            agent = EvidenceContradictionDecomposerAgent(self.llm)
            output = await agent.run(state, arguments)
            return ActionResult(output=output)

        if name == "keyword_search_agent":
            KeywordSearchAgent = _execution_agent_class("keyword_search_agent", "KeywordSearchAgent")
            agent = KeywordSearchAgent(self.tools)
            output = await agent.run(state, arguments, prompt_context)
            loop_state = prompt_context.get("loop_state_name", "evidence_planning_and_tool_use")
            selected_by_llm = bool(prompt_context.get("selected_by_llm", True))
            whitelist_checked = bool(prompt_context.get("tool_whitelist") is not None)
            for trace in output.get("tool_traces", []):
                if isinstance(trace, dict):
                    trace["requested_by_state"] = loop_state
                    trace["selected_by_llm"] = selected_by_llm
                    trace["whitelist_checked"] = whitelist_checked
                    trace["subagent"] = "keyword_search_agent"
            return ActionResult(output=output)

        if name == "entity_resolution_agent":
            output = await EntityResolutionAgent(self.tools).run(state, arguments, prompt_context)
            return self._annotate_subagent_output(output, name, prompt_context)

        if name == "nearby_anchor_strategy_agent":
            NearbyAnchorStrategyAgent = _module(
                "app.planning.nearby_anchor_strategy"
            ).NearbyAnchorStrategyAgent
            output = await NearbyAnchorStrategyAgent().run(state, arguments, prompt_context)
            return self._annotate_subagent_output(output, name, prompt_context)

        if name == "route_feasibility_agent":
            RouteFeasibilityAgent = _execution_agent_class("route_feasibility_agent", "RouteFeasibilityAgent")
            output = await RouteFeasibilityAgent(self.tools).run(state, arguments, prompt_context)
            return self._annotate_subagent_output(output, name, prompt_context)

        if name == "fact_search_agent":
            FactSearchAgent = _execution_agent_class("fact_search_agent", "FactSearchAgent")
            output = await FactSearchAgent(self.tools).run(state, arguments, prompt_context)
            return self._annotate_subagent_output(output, name, prompt_context)

        if name == "fact_lookup_agent":
            FactLookupAgent = _execution_agent_class("fact_lookup_agent", "FactLookupAgent")
            output = await FactLookupAgent(self.tools).run(state, arguments, prompt_context)
            return self._annotate_subagent_output(output, name, prompt_context)

        if name == "weather_context_agent":
            WeatherContextAgent = _execution_agent_class("weather_context_agent", "WeatherContextAgent")
            output = await WeatherContextAgent(self.tools).run(state, arguments, prompt_context)
            return self._annotate_subagent_output(output, name, prompt_context)

        return ActionResult(ok=False, error=f"Unknown subagent: {name}")

    def _annotate_subagent_output(self, output: dict, name: str, prompt_context: dict) -> ActionResult:
        loop_state = prompt_context.get("loop_state_name", "evidence_planning_and_tool_use")
        selected_by_llm = bool(prompt_context.get("selected_by_llm", True))
        whitelist_checked = bool(prompt_context.get("tool_whitelist") is not None)
        for trace in output.get("tool_traces", []):
            if isinstance(trace, dict):
                trace["requested_by_state"] = loop_state
                trace["selected_by_llm"] = selected_by_llm
                trace["whitelist_checked"] = whitelist_checked
                trace["subagent"] = name
        return ActionResult(output=output)

    async def _call_tool(
        self,
        tool_name: str,
        arguments: dict,
        state: Any,
        prompt_context: dict,
    ) -> ActionResult:
        if not self.tools:
            return ActionResult(ok=False, error="Tool registry unavailable")

        resolved = resolve_tool_name(tool_name)
        phase = "gap_fill" if prompt_context.get("gap_filling") else (
            "supplement" if not prompt_context.get("selected_by_llm", True) else "main"
        )
        claim = (
            arguments.get("claim_target")
            or arguments.get("information_need")
            or (prompt_context.get("gap_request") or {}).get("claim_type")
        )
        try:
            payload = self._build_tool_arguments(resolved, arguments, state, prompt_context)
        except ValueError as exc:
            from app.execution.s5_tool_attempt_ledger import record_tool_attempt

            msg = str(exc)
            logger.info("CALL_TOOL %s skipped (args): %s", resolved, msg)
            record_tool_attempt(
                state,
                tool_name=resolved,
                claim_type=str(claim) if claim else None,
                phase=phase,
                status="skipped_invalid_args",
                evidence_count=0,
                error=msg,
            )
            return ActionResult(
                ok=False,
                error=msg,
                output={
                    "evidence": [],
                    "tool_name": resolved,
                    "policy_tool_name": tool_name,
                    "tool_traces": [],
                    "skipped": True,
                },
            )
        trace_before = len(self.tools.traces)

        try:
            try_java_tool_gateway = _module("app.integrations.java_gateway.integration").try_java_tool_gateway
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
            from app.execution.s5_tool_attempt_ledger import record_tool_attempt

            record_tool_attempt(
                state,
                tool_name=resolved,
                claim_type=str(claim) if claim else None,
                phase=phase,
                status="ok" if evidence else "zero_evidence",
                evidence_count=len(evidence),
            )
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
            from app.execution.s5_tool_attempt_ledger import record_tool_attempt

            record_tool_attempt(
                state,
                tool_name=resolved,
                claim_type=str(claim) if claim else None,
                phase=phase,
                status="error",
                evidence_count=0,
                error=str(exc),
            )
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
        state: Any,
        prompt_context: dict,
    ) -> dict:
        enrich_mcp_tool_arguments = _module("app.integrations.mcp.tool_arguments").enrich_mcp_tool_arguments

        return enrich_mcp_tool_arguments(
            tool_name,
            arguments,
            state=state,
            prompt_context=prompt_context,
        )

    def _annotate_traces(self, trace_before: int, policy_tool_name: str, prompt_context: dict) -> None:
        if not self.tools or len(self.tools.traces) <= trace_before:
            return

        loop_state = prompt_context.get("loop_state_name", "evidence_planning_and_tool_use")
        selected_by_llm = bool(prompt_context.get("selected_by_llm", True))
        whitelist_checked = bool(prompt_context.get("tool_whitelist") is not None)

        annotated: list[Any] = []
        for trace in self.tools.traces[trace_before:]:
            input_data = dict(trace.input or {})
            if policy_tool_name == "baidu_ip_location_mcp":
                input_data.setdefault("location_sensitive", True)
            annotated.append(
                trace.model_copy(
                    update={
                        "requested_by_state": loop_state,
                        "selected_by_llm": selected_by_llm,
                        "whitelist_checked": whitelist_checked,
                        "tool_name": policy_tool_name if trace.tool_name != policy_tool_name else trace.tool_name,
                        "input": input_data,
                    }
                )
            )
        self.tools.traces[trace_before:] = annotated
