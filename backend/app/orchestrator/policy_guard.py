from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.state_policy import StateNodePolicy


class PolicyGuard:
    """Validate that model-proposed actions stay within state policy."""

    def validate(self, action: AgentAction, policy: StateNodePolicy) -> None:
        if action.action_type not in policy.allowed_actions:
            raise ValueError(
                f"Action {action.action_type.value} not allowed in state {policy.state_name}"
            )

        if action.action_type == AgentActionType.CALL_SUBAGENT:
            if not action.target:
                raise ValueError("CALL_SUBAGENT requires target subagent name")
            if action.target not in policy.allowed_subagents:
                raise ValueError(
                    f"Subagent {action.target!r} not allowed in state {policy.state_name}"
                )

        if action.action_type == AgentActionType.CALL_TOOL:
            if not action.target:
                raise ValueError("CALL_TOOL requires target tool name")
            if action.target not in policy.allowed_tools:
                raise ValueError(
                    f"Tool {action.target!r} not allowed in state {policy.state_name}"
                )

        if action.action_type == AgentActionType.FINISH_STATE and policy.allow_final_answer:
            if not action.arguments.get("final_response") and not action.reason_summary:
                pass
