from app.orchestrator.action_executor import ActionExecutor
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard
from app.orchestrator.policy_guard import PolicyGuard
from app.orchestrator.state_policy import StateNodePolicy
from app.orchestrator.state_reducer import StateReducer
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState


class ClaudeStateRunner:
    """Controlled Claude-style loop: policy → action → execute → reduce → repeat."""

    def __init__(
        self,
        llm_client=None,
        tools=None,
        *,
        model_controller: ActionModelController | None = None,
        action_executor: ActionExecutor | None = None,
        state_reducer: StateReducer | None = None,
        policy_guard: PolicyGuard | None = None,
    ) -> None:
        self.model_controller = model_controller or ActionModelController(llm_client)
        self.action_executor = action_executor or ActionExecutor(llm_client, tools)
        self.state_reducer = state_reducer or StateReducer()
        self.policy_guard = policy_guard or PolicyGuard()

    async def run(
        self,
        state: TravelAgentState,
        policy: StateNodePolicy,
        prompt_context: dict | None = None,
    ) -> TravelAgentState:
        ctx = prompt_context or {}
        TraceRecorder.add(state, f"✓ 进入受控状态循环：{policy.state_name}")
        tool_call_count = int(ctx.get("tool_call_count", 0))

        for step in range(policy.max_steps):
            action = await self.model_controller.next_action(state, policy, ctx, step)
            ctx["selected_by_llm"] = ctx.get("_last_action_source") == "llm"
            ctx.setdefault("loop_state_name", policy.state_name)
            try:
                tool_whitelist = ctx.get("tool_whitelist")
                guard_kwargs = {"tool_call_count": tool_call_count}
                if isinstance(self.policy_guard, EvidencePolicyGuard):
                    self.policy_guard.validate(
                        action, policy, state, tool_whitelist=tool_whitelist, **guard_kwargs
                    )
                else:
                    self.policy_guard.validate(action, policy, state, tool_whitelist=tool_whitelist)
            except ValueError as exc:
                state.limitations.append(str(exc))
                TraceRecorder.add(state, f"✗ [{policy.state_name}] policy 拒绝：{exc}")
                break

            TraceRecorder.add(
                state,
                f"✓ [{policy.state_name}] step {step + 1}: {action.action_type.value}"
                + (f" → {action.target}" if action.target else ""),
            )

            if action.action_type == AgentActionType.FINISH_STATE:
                state = self.state_reducer.apply_finish(state, action, policy)
                return state

            if action.action_type == AgentActionType.FAIL_STATE:
                state = self.state_reducer.apply(state, action, action_executor_result_fail(action), policy)
                return state

            result = await self.action_executor.execute(action, state, ctx)
            state = self.state_reducer.apply(state, action, result, policy)
            if action.action_type == AgentActionType.CALL_SUBAGENT:
                sub_calls = int((result.output or {}).get("tool_call_count", 0))
                if sub_calls:
                    tool_call_count += sub_calls
                    ctx["tool_call_count"] = tool_call_count
            if action.action_type in {
                AgentActionType.CALL_TOOL,
                AgentActionType.CALL_SUBAGENT,
            }:
                if action.action_type == AgentActionType.CALL_TOOL:
                    tool_call_count += 1
                    ctx["tool_call_count"] = tool_call_count
                if state.response_contract:
                    from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker

                    state.coverage_report = EvidenceCoverageChecker().check(
                        state.response_contract,
                        state.evidence,
                        state.tool_traces,
                    )
                if action.action_type == AgentActionType.CALL_TOOL:
                    clarify_state = await self._maybe_baidu_disambiguation(
                        state, action, policy, ctx
                    )
                    if clarify_state is not None:
                        return clarify_state

        state.limitations.append(f"{policy.state_name} reached max_steps")
        TraceRecorder.add(state, f"✓ [{policy.state_name}] 达到 max_steps={policy.max_steps}")
        return state

    async def _maybe_baidu_disambiguation(
        self,
        state: TravelAgentState,
        action: AgentAction,
        policy: StateNodePolicy,
        ctx: dict,
    ) -> TravelAgentState | None:
        if policy.state_name != "evidence_planning_and_tool_use":
            return None
        if action.action_type != AgentActionType.CALL_TOOL:
            return None
        if (action.target or "") != "baidu_place_search_mcp":
            return None

        from app.orchestrator.place_disambiguation_guard import (
            apply_unique_candidate,
            build_clarification_question,
            detect_ambiguous_candidates,
            extract_place_candidates,
            should_apply_unique_resolution,
        )

        ambiguous = detect_ambiguous_candidates(state.evidence)
        if ambiguous:
            frame = state.semantic_frame
            place = (
                frame.entities.places[0]
                if frame and frame.entities.places
                else state.raw_user_query
            )
            question = build_clarification_question(place, ambiguous)
            clarify = AgentAction(
                action_type=AgentActionType.ASK_CLARIFICATION,
                arguments={
                    "question": question,
                    "missing_critical_info": ["place_disambiguation"],
                },
                reason_summary="Baidu place search returned multiple candidates",
            )
            result = await self.action_executor.execute(clarify, state, ctx)
            state = self.state_reducer.apply(state, clarify, result, policy)
            TraceRecorder.add(state, "✓ [S5] place disambiguation clarification required")
            return state

        candidates = extract_place_candidates(state.evidence)
        unique = should_apply_unique_resolution(candidates)
        if unique:
            state = apply_unique_candidate(state, unique)
            TraceRecorder.add(
                state,
                f"✓ [S5] resolved place via Baidu: {unique.get('province', '')} {unique.get('city', '')}",
            )
        return None


def action_executor_result_fail(action):
    from app.orchestrator.actions import ActionResult

    return ActionResult(
        ok=False,
        error=action.reason_summary or "state failed",
        output=action.arguments,
    )
