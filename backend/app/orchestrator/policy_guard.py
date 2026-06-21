from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.state_policy import StateNodePolicy
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState


class PolicyGuard:
    """Validate that model-proposed actions stay within state policy."""

    def validate(
        self,
        action: AgentAction,
        policy: StateNodePolicy,
        state: TravelAgentState | None = None,
        tool_whitelist: ToolWhitelist | None = None,
    ) -> None:
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
            self._validate_dynamic_whitelist(action, tool_whitelist)

        if action.action_type == AgentActionType.FINISH_STATE and policy.allow_final_answer:
            if not action.arguments.get("final_response") and not action.reason_summary:
                pass

    @staticmethod
    def _validate_dynamic_whitelist(
        action: AgentAction,
        tool_whitelist: ToolWhitelist | None,
    ) -> None:
        if tool_whitelist is None:
            return

        target = action.target or ""
        allowed_names = tool_whitelist.allowed_tool_names()
        if target not in allowed_names:
            hint = ", ".join(allowed_names[:12])
            raise ValueError(
                f"Tool {target!r} not in dynamic whitelist for this task; "
                f"choose from: [{hint}]"
            )

        descriptor = tool_whitelist.get_descriptor(target)
        if descriptor is None:
            raise ValueError(f"Tool {target!r} missing from whitelist descriptors.")

        if not descriptor.configured:
            reason = tool_whitelist.reason_by_tool.get(target, "Tool not configured.")
            raise ValueError(
                f"Tool {target!r} is not configured for this environment: {reason}"
            )
