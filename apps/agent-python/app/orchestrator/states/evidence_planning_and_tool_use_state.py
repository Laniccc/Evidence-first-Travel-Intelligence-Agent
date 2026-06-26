from datetime import date

from app.agents.information_need_planner import InformationNeedPlanner
from app.config import get_settings
from app.orchestrator.action_executor import ActionExecutor
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.comparison_helpers import comparison_max_tool_calls, is_comparison_mode
from app.orchestrator.state_policy import EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
from app.orchestrator.state_reducer import StateReducer
from app.orchestrator.tool_whitelist_builder import ToolWhitelistBuilder
from app.orchestrator.trace import TraceRecorder
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.evidence import Evidence
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry
from app.tools.mcp.tool_specs import NEED_TOOL_PROFILES
from app.tools.tool_name_resolver import resolve_tool_name
from app.tools.tool_router import ToolRouter
from tools.mcp.http_autostart import ensure_http_mcp_services


class EvidencePlanningAndToolUseState:
    """S5: controlled loop for evidence retrieval / tool use (no cross-source judgement)."""

    def __init__(
        self,
        llm_client=None,
        tools=None,
        tool_router: ToolRouter | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.tools = tools
        self.tool_router = tool_router
        self.capability_registry = capability_registry or CapabilityRegistry()
        self.whitelist_builder = ToolWhitelistBuilder(self.capability_registry, tools)
        self.runner = ClaudeStateRunner(
            llm_client,
            tools,
            policy_guard=EvidencePolicyGuard(),
        )

    async def run(self, state: TravelAgentState, **ctx) -> TravelAgentState:
        settings = get_settings()
        if settings.mcp_enabled and settings.mcp_http_autostart:
            for note in await ensure_http_mcp_services(settings):
                TraceRecorder.add(state, f"✓ S5 MCP autostart: {note}")

        if state.travel_task and not state.information_needs:
            state.information_needs = InformationNeedPlanner.plan(state.travel_task)

        tool_whitelist = self.whitelist_builder.build(state, ctx)
        prompt_context = self._build_prompt_context(state, ctx, tool_whitelist)
        if state.s5_domain_plan and state.s5_domain_plan.domains:
            TraceRecorder.add(
                state,
                "✓ S5 信息域规划："
                + ", ".join(d.value for d in state.s5_domain_plan.domains),
            )
            groups = state.s5_domain_plan.provider_groups()
            if groups:
                TraceRecorder.add(
                    state,
                    "✓ S5 provider groups："
                    + ", ".join(g.value for g in groups),
                )
        if ctx.get("reset_evidence", True):
            state.evidence = []

        TraceRecorder.add(
            state,
            f"✓ S5 动态工具白名单：{', '.join(tool_whitelist.allowed_tool_names()) or '（空）'}",
        )
        for tool_name in tool_whitelist.blocked_tools[:12]:
            reason = tool_whitelist.reason_by_tool.get(tool_name, "blocked")
            TraceRecorder.add(state, f"⊘ S5 blocked {tool_name}: {reason}")

        state = await self.runner.run(state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, prompt_context)
        state = await self._supplement_answer_mode_tools(state, prompt_context, tool_whitelist)
        if self.tools and not state.tool_traces:
            state.tool_traces = list(self.tools.traces)
        if not state.evidence_planning_completed:
            state.evidence_planning_completed = True
            TraceRecorder.add(state, "✓ EvidencePlanning 达到 max_steps 或异常结束")
        else:
            TraceRecorder.add(state, "✓ 已完成 EvidencePlanningAndToolUse")
        return state

    async def run_gap_filling(self, state: TravelAgentState, gap) -> TravelAgentState:
        from app.config import get_settings
        from app.schemas.evidence_gap_request import EvidenceGapRequest

        if not isinstance(gap, EvidenceGapRequest):
            gap = EvidenceGapRequest.model_validate(gap)
        gap.ensure_signature()
        state.current_evidence_gap_request = gap
        from app.orchestrator.ticket_lookup_policy import apply_ticket_gap_phase_override

        apply_ticket_gap_phase_override(state, gap)
        settings = get_settings()
        tool_whitelist = self.whitelist_builder.build_gap_whitelist(gap)
        prompt_context = {
            "gap_filling": True,
            "gap_request": gap.model_dump(),
            "gap_query_objectives": [o.model_dump() for o in gap.query_objectives],
            "gap_query_objective": gap.query_objective,
            "gap_max_extra_steps": min(gap.max_extra_steps, settings.evidence_gap_max_extra_steps),
            "reset_evidence": False,
            "place_name": (
                state.comparison_active_place
                or (
                    state.semantic_frame.entities.places[0]
                    if state.semantic_frame and state.semantic_frame.entities.places
                    else None
                )
            ),
        }
        prompt_context["tool_whitelist"] = tool_whitelist
        prompt_context["allowed_tools"] = [t.model_dump() for t in tool_whitelist.allowed_tools]
        from app.orchestrator.s5_diversified_tool_selector import store_retrieval_plans

        store_retrieval_plans(state, tool_whitelist)
        TraceRecorder.add(
            state,
            f"✓ S5 gap-filling：{gap.claim_type} tools={tool_whitelist.allowed_tool_names()}",
        )
        before = len(state.evidence)
        state = await self.runner.run(state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, prompt_context)
        if self.tools and not state.tool_traces:
            state.tool_traces = list(self.tools.traces)
            for trace in state.tool_traces[-settings.evidence_gap_max_extra_steps :]:
                trace.gap_filling = True
                trace.gap_id = gap.gap_id
                trace.gap_claim_type = gap.claim_type
        state.current_evidence_gap_request = None
        if len(state.evidence) > before:
            if state.gap_loop_state:
                state.gap_loop_state.resolved_gap_ids.append(gap.gap_id)
        else:
            if state.gap_loop_state:
                state.gap_loop_state.failed_gap_ids.append(gap.gap_id)
        TraceRecorder.add(state, f"✓ S5 gap-filling 完成：+{len(state.evidence) - before} evidence")
        return state

    def _build_prompt_context(
        self,
        state: TravelAgentState,
        ctx: dict,
        tool_whitelist: ToolWhitelist,
    ) -> dict:
        prompt_context = dict(ctx)
        prompt_context["tool_whitelist"] = tool_whitelist
        prompt_context["allowed_tools"] = [t.model_dump() for t in tool_whitelist.allowed_tools]
        # LLM-facing context: only dynamic allowed_tools (no static state-policy tool catalog).
        prompt_context.pop("candidate_tool_plan", None)
        prompt_context["s5_prompt_rules"] = [
            "S5 orchestrator LLM plans each step — CALL_SUBAGENT only (no direct CALL_TOOL).",
            "Functional subagents: entity_resolution_agent, route_feasibility_agent, "
            "fact_search_agent, weather_context_agent, evidence_contradiction_decomposer_agent.",
            "Each subagent executes MCP from the shared whitelist using its tool_priority profile.",
            "Pass lookup_intent, claim_target, search_query, anchor_keywords, tool_parameters in arguments.",
            "China place without city → entity_resolution_agent first (handles 同名消歧 internally).",
            "Distance/day-trip → route_feasibility_agent with origin+destination in tool_parameters.",
            "Hard facts → fact_search_agent after entity anchored when possible.",
            "Read subagent_results each step; finish_state when user purpose met or coverage sufficient.",
            "Do NOT generate final answer text in this state.",
        ]
        from app.agents.s5_subagent_registry import subagent_definitions_for_prompt

        prompt_context["subagent_definitions"] = subagent_definitions_for_prompt()
        from app.orchestrator.s5_diversified_tool_selector import (
            diversity_hints_for_state,
            store_retrieval_plans,
        )

        store_retrieval_plans(state, tool_whitelist)
        diversified = diversity_hints_for_state(state, tool_whitelist)
        legacy = self._tool_diversity_hints(state, tool_whitelist)
        prompt_context["tool_diversity_hints"] = diversified + [h for h in legacy if h not in diversified]

        if state.travel_task:
            candidate_needs = InformationNeedPlanner.plan(state.travel_task)
            if not state.information_needs:
                prompt_context["candidate_information_needs"] = [n.model_dump() for n in candidate_needs]
            if self.tool_router:
                plan = self.tool_router.route(
                    state.information_needs or candidate_needs,
                    state.travel_task,
                )
                state.tool_execution_plan = plan

        frame = state.semantic_frame
        current_place = ctx.get("place_name") or (
            state.comparison_active_place
            if state.comparison_active_place
            else (frame.entities.places[0] if frame and frame.entities.places else None)
        )
        if current_place:
            prompt_context["place_name"] = current_place
        if frame:
            prompt_context.setdefault("city", frame.entities.city)
            prompt_context.setdefault("country", frame.entities.country)

        from app.orchestrator.comparison_helpers import is_comparison_mode

        if is_comparison_mode(state):
            prompt_context["comparison_mode"] = True
            prompt_context["comparison_peer_places"] = list(state.comparison_peer_places or [])

        if state.normalized_request:
            prompt_context["normalized_request"] = state.normalized_request.model_dump()

        if state.answer_mode_decision:
            prompt_context["answer_mode_decision"] = state.answer_mode_decision.model_dump()

        if state.response_contract:
            prompt_context["response_contract"] = state.response_contract.model_dump()
            prompt_context["claim_search_max_attempts"] = ClaimSearchPlanner.max_search_attempts(state)
        if state.coverage_report:
            prompt_context["coverage_report"] = state.coverage_report.model_dump()

        if state.user_need_residual:
            prompt_context["user_need_residual"] = state.user_need_residual.model_dump()

        from app.orchestrator.agent_tool_catalog import agent_tool_definitions_for_allowed, resolve_s5_task_class

        allowed_names = tool_whitelist.allowed_tool_names()
        task_class = resolve_s5_task_class(state)
        prompt_context["s5_task_class"] = task_class
        prompt_context["agent_tool_definitions"] = agent_tool_definitions_for_allowed(
            allowed_names,
            task_class=task_class,
        )
        from app.orchestrator.nearby_task_orchestration import nearby_s5_planning_context
        from app.orchestrator.fact_lookup_task_orchestration import fact_s5_planning_context

        prompt_context.update(nearby_s5_planning_context(state))
        prompt_context.update(fact_s5_planning_context(state))
        from app.orchestrator.lookup_research_chain import build_lookup_research_context

        prompt_context["lookup_research_chain"] = build_lookup_research_context(state)
        structured = dict(state.structured_result or {})
        structured["_agent_tool_definitions"] = prompt_context["agent_tool_definitions"]
        state.structured_result = structured

        prompt_context["blocked_tools"] = tool_whitelist.blocked_tools
        prompt_context["whitelist_policy_notes"] = tool_whitelist.policy_notes
        prompt_context["current_date"] = str(date.today())
        max_calls = (
            comparison_max_tool_calls()
            if is_comparison_mode(state)
            else get_settings().mcp_max_tool_calls_per_state
        )
        prompt_context["max_tool_calls"] = max_calls
        prompt_context["tool_call_count"] = 0
        prompt_context["evidence_policy_summary"] = self._evidence_policy_summary(state)
        prompt_context["current_evidence_summary"] = self._evidence_summary(state.evidence)
        if state.conversation_context:
            ctx = state.conversation_context
            prompt_context["conversation_context"] = (
                ctx.model_dump() if hasattr(ctx, "model_dump") else ctx
            )
        return prompt_context

    @staticmethod
    def _residual_need_types(state: TravelAgentState) -> list[str]:
        residual = state.user_need_residual
        if not residual:
            return []
        types = [n.need_type for n in residual.information_needs if n.need_type]
        for claim in residual.claim_requirements:
            if claim.claim_type and claim.claim_type not in types:
                types.append(claim.claim_type)
        return types

    @staticmethod
    def _tool_diversity_hints(state: TravelAgentState, tool_whitelist: ToolWhitelist) -> list[str]:
        hints: list[str] = []
        allowed = set(tool_whitelist.allowed_tool_names())
        residual = state.user_need_residual
        needs = EvidencePlanningAndToolUseState._residual_need_types(state)
        frame = state.semantic_frame
        if not needs and frame:
            needs = list(frame.information_needs)
        if "ticket_price" in needs:
            for tool in (
                "official_page_reader_mcp",
                "browser_mcp",
                "baidu_place_detail_mcp",
                "ticketlens_experience_mcp",
                "ctrip_ticket_signal_crawler_mcp",
                "fliggy_ticket_snapshot_crawler_mcp",
            ):
                if tool in allowed:
                    hints.append(f"ticket_price: try CALL_TOOL {tool} before repeated search_mcp")
        if "opening_hours" in needs:
            for tool in ("official_page_reader_mcp", "baidu_place_detail_mcp", "official"):
                if tool in allowed:
                    hints.append(f"opening_hours: try CALL_TOOL {tool}")
        if "seasonal_operation_status" in needs or (
            residual and residual.time_scope == "current" and residual.requires_live_data
        ):
            for tool in (
                "official_source_discovery_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
                "baidu_traffic_mcp",
            ):
                if tool in allowed:
                    hints.append(
                        f"operational status: try CALL_TOOL {tool} for current open/closure notices"
                    )
        if is_comparison_mode(state):
            for tool in (
                "ctrip_review_crawler_mcp",
                "dianping_review_crawler_mcp",
                "baidu_route_matrix_mcp",
                "baidu_route_mcp",
            ):
                if tool in allowed:
                    hints.append(f"comparison: try CALL_TOOL {tool} for per-place or route evidence")
        from app.orchestrator.evidence_signal_utils import is_day_trip_query

        route_needs = {
            "distance",
            "duration",
            "route_plan",
            "transport_planning",
            "itinerary_feasibility",
            "transit",
        }
        needs_route = bool(set(needs) & route_needs)
        if frame and is_day_trip_query(frame):
            needs_route = True
        if needs_route:
            if "baidu_place_search_mcp" in allowed:
                hints.append(
                    "day-trip/route: CALL_TOOL baidu_place_search_mcp first to resolve destination POI"
                )
            if "baidu_route_mcp" in allowed:
                hints.append(
                    "day-trip/route: delegate keyword_search_agent task with tool_parameters "
                    "origin→destination and preferred_tool=baidu_route_mcp before judging 一日游是否够用"
                )
        return hints

    @staticmethod
    def _evidence_policy_summary(state: TravelAgentState) -> dict:
        needs = EvidencePlanningAndToolUseState._residual_need_types(state)
        frame = state.semantic_frame
        if not needs and frame:
            needs = list(frame.information_needs)
        return {
            need: {
                "model_prior_allowed": EvidencePolicy.model_prior_allowed_for(need),
                "requires_evidence": EvidencePolicy.requires_evidence_for(need),
            }
            for need in needs
        }

    @staticmethod
    def _evidence_summary(evidence: list) -> list[dict]:
        summary: list[dict] = []
        for ev in evidence:
            if not isinstance(ev, Evidence):
                continue
            summary.append(
                {
                    "evidence_id": ev.evidence_id,
                    "source_name": ev.source_name,
                    "claim_types": [c.claim_type.value for c in ev.claims],
                    "confidence": ev.confidence,
                }
            )
        return summary

    async def _supplement_answer_mode_tools(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        tool_whitelist: ToolWhitelist,
    ) -> TravelAgentState:
        """Ensure AnswerModeDecision required/optional tools get at least one attempt."""
        decision = state.answer_mode_decision
        if not decision or not self.tools:
            return state

        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        pending = self._supplement_tool_order(state, decision, tool_whitelist)
        executor = ActionExecutor(self.llm_client, self.tools)
        reducer = StateReducer()
        allowed_names = set(tool_whitelist.allowed_tool_names())

        tool_call_count = int(prompt_context.get("tool_call_count", 0))
        max_calls = int(
            prompt_context.get("max_tool_calls")
            or (
                comparison_max_tool_calls()
                if is_comparison_mode(state)
                else get_settings().mcp_max_tool_calls_per_state
            )
        )

        for tool in pending:
            if tool_call_count >= max_calls:
                break
            if tool not in allowed_names:
                continue
            resolved = resolve_tool_name(tool)
            if resolved in called:
                continue
            from app.orchestrator.actions import AgentAction, AgentActionType

            action = AgentAction(
                action_type=AgentActionType.CALL_TOOL,
                target=tool,
                arguments={},
                reason_summary=f"Supplement AnswerMode tool: {tool}",
            )
            try:
                EvidencePolicyGuard().validate(
                    action,
                    EVIDENCE_PLANNING_AND_TOOL_USE_POLICY,
                    state,
                    tool_whitelist=tool_whitelist,
                    tool_call_count=tool_call_count,
                )
            except ValueError:
                continue

            supplement_ctx = {
                **prompt_context,
                "selected_by_llm": False,
                "loop_state_name": "evidence_planning_and_tool_use",
                "tool_call_count": tool_call_count,
            }
            result = await executor.execute(action, state, supplement_ctx)
            state = reducer._apply_tool_result(
                state, action, result, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY
            )
            called.add(resolved)
            tool_call_count += 1
            TraceRecorder.add(state, f"✓ [supplement] CALL_TOOL {tool} (selected_by_llm=false)")

        return state

    def _supplement_tool_order(
        self,
        state: TravelAgentState,
        decision,
        tool_whitelist: ToolWhitelist,
    ) -> list[str]:
        """Order supplement tools by diversified selector queue, then NEED_TOOL_PROFILES."""
        from app.orchestrator.s5_diversified_tool_selector import S5DiversifiedToolSelector

        selector = S5DiversifiedToolSelector(state)
        diversified = selector.non_search_tool_queue(tool_whitelist)
        frame = state.semantic_frame
        hard_needs = []
        if frame:
            hard_needs = [n for n in frame.information_needs if n in NEED_TOOL_PROFILES]

        profile_order: list[str] = []
        for need in hard_needs:
            for tool in NEED_TOOL_PROFILES.get(need, []):
                if tool not in profile_order:
                    profile_order.append(tool)

        raw = list(decision.required_tools or []) + list(decision.optional_tools or [])
        merged = diversified + profile_order + raw
        ordered: list[str] = []
        for tool in merged:
            resolved = resolve_tool_name(tool)
            if resolved not in ordered:
                ordered.append(resolved)
        return ordered
