from datetime import date

from app.agents.information_need_planner import InformationNeedPlanner
from app.config import get_settings
from app.orchestrator.action_executor import ActionExecutor
from app.orchestrator.claude_state_runner import ClaudeStateRunner
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
    """S5+S6: controlled loop for information-need planning and tool/MCP execution."""

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

        tool_whitelist = self.whitelist_builder.build(state)
        prompt_context = self._build_prompt_context(state, ctx, tool_whitelist)
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
            "CALL_TOOL target MUST be one of allowed_tools[].name — no other tools.",
            "Do NOT generate final answer text in this state.",
            "If tools are insufficient, FINISH_STATE with limitations or use an allowed fallback tool.",
            "You may call multiple tools across steps until evidence is sufficient or max_steps reached.",
        ]

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
