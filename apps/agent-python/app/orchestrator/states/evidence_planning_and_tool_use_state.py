from datetime import date

from app.agents.information_need_planner import InformationNeedPlanner
from app.config import get_settings
from app.orchestrator.action_executor import ActionExecutor
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
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
        if self.tools:
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
        settings = get_settings()
        tool_whitelist = self.whitelist_builder.build_gap_whitelist(gap)
        prompt_context = {
            "gap_filling": True,
            "gap_request": gap.model_dump(),
            "gap_max_extra_steps": min(gap.max_extra_steps, settings.evidence_gap_max_extra_steps),
            "reset_evidence": False,
            "place_name": (state.semantic_frame.entities.places[0] if state.semantic_frame and state.semantic_frame.entities.places else None),
        }
        prompt_context["tool_whitelist"] = tool_whitelist
        prompt_context["allowed_tools"] = [t.model_dump() for t in tool_whitelist.allowed_tools]
        TraceRecorder.add(
            state,
            f"✓ S5 gap-filling：{gap.claim_type} tools={tool_whitelist.allowed_tool_names()}",
        )
        before = len(state.evidence)
        state = await self.runner.run(state, EVIDENCE_PLANNING_AND_TOOL_USE_POLICY, prompt_context)
        if self.tools:
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
            "Return ONLY one AgentAction JSON per step.",
            "Prefer CALL_SUBAGENT search_task_planner_agent / keyword_search_agent over CALL_TOOL.",
            "keyword_search_agent args: anchor_keywords (S4), search_query, information_need (search purpose).",
            "preferred_tool on tasks is optional; keyword_search_agent picks MCP from whitelist.",
            "place_candidates in evidence are normal tool output — refine queries, do not ASK_CLARIFICATION in S5.",
            "Every 2 keyword_search completions triggers search_task_planner refine (max 10 searches per S5).",
            "When multiple price/hour values appear, evidence_contradiction_decomposer_agent splits by ticket tier/season.",
            "CALL_TOOL only for one-off geo when subagents cannot cover.",
            "Do NOT generate final answer text in this state.",
        ]
        prompt_context["tool_diversity_hints"] = self._tool_diversity_hints(state, tool_whitelist)

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
        if frame:
            prompt_context.setdefault(
                "place_name",
                (frame.entities.places[0] if frame.entities.places else None),
            )
            prompt_context.setdefault("city", frame.entities.city)
            prompt_context.setdefault("country", frame.entities.country)

        if state.normalized_request:
            prompt_context["normalized_request"] = state.normalized_request.model_dump()

        if state.answer_mode_decision:
            prompt_context["answer_mode_decision"] = state.answer_mode_decision.model_dump()

        if state.response_contract:
            prompt_context["response_contract"] = state.response_contract.model_dump()
            prompt_context["claim_search_max_attempts"] = ClaimSearchPlanner.max_search_attempts(state)
        if state.coverage_report:
            prompt_context["coverage_report"] = state.coverage_report.model_dump()

        prompt_context["blocked_tools"] = tool_whitelist.blocked_tools
        prompt_context["whitelist_policy_notes"] = tool_whitelist.policy_notes
        prompt_context["current_date"] = str(date.today())
        prompt_context["max_tool_calls"] = get_settings().mcp_max_tool_calls_per_state
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
    def _tool_diversity_hints(state: TravelAgentState, tool_whitelist: ToolWhitelist) -> list[str]:
        hints: list[str] = []
        allowed = set(tool_whitelist.allowed_tool_names())
        frame = state.semantic_frame
        needs = list(frame.information_needs) if frame else []
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
        return hints

    @staticmethod
    def _evidence_policy_summary(state: TravelAgentState) -> dict:
        frame = state.semantic_frame
        needs = list(frame.information_needs) if frame else []
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
        pending = self._supplement_tool_order(state, decision)
        executor = ActionExecutor(self.llm_client, self.tools)
        reducer = StateReducer()
        allowed_names = set(tool_whitelist.allowed_tool_names())

        tool_call_count = int(prompt_context.get("tool_call_count", 0))
        max_calls = get_settings().mcp_max_tool_calls_per_state

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

    def _supplement_tool_order(self, state: TravelAgentState, decision) -> list[str]:
        """Order supplement tools by NEED_TOOL_PROFILES priority for hard-fact needs."""
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
        if profile_order:
            ordered = [t for t in profile_order if t in raw]
            ordered += [t for t in raw if t not in ordered]
            return ordered
        return raw
