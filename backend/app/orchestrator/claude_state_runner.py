from app.orchestrator.action_executor import ActionExecutor
from app.orchestrator.action_model_controller import ActionModelController
from app.orchestrator.actions import AgentActionType
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

        for step in range(policy.max_steps):
            action = await self.model_controller.next_action(state, policy, ctx, step)
            try:
                self.policy_guard.validate(action, policy)
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

        state.limitations.append(f"{policy.state_name} reached max_steps")
        TraceRecorder.add(state, f"✓ [{policy.state_name}] 达到 max_steps={policy.max_steps}")
        return state


def action_executor_result_fail(action):
    from app.orchestrator.actions import ActionResult

    return ActionResult(
        ok=False,
        error=action.reason_summary or "state failed",
        output=action.arguments,
    )
