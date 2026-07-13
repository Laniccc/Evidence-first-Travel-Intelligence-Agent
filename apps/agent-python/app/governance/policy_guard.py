"""Run policy enforcement independent of orchestration implementations."""

from typing import Any


class PolicyGuard:
    """Validate model-proposed actions against a state policy and whitelist."""

    def validate(
        self,
        action: Any,
        policy: Any,
        state: Any | None = None,
        tool_whitelist: Any | None = None,
    ) -> None:
        if action.action_type not in policy.allowed_actions:
            raise ValueError(
                f"Action {action.action_type.value} not allowed in state {policy.state_name}"
            )

        action_type = getattr(action.action_type, "value", action.action_type)
        if action_type == "call_subagent":
            if not action.target:
                raise ValueError("CALL_SUBAGENT requires target subagent name")
            if action.target not in policy.allowed_subagents:
                raise ValueError(
                    f"Subagent {action.target!r} not allowed in state {policy.state_name}"
                )

        if action_type == "call_tool":
            if not action.target:
                raise ValueError("CALL_TOOL requires target tool name")
            if action.target not in policy.allowed_tools:
                raise ValueError(
                    f"Tool {action.target!r} not allowed in state {policy.state_name}"
                )
            self._validate_dynamic_whitelist(action, tool_whitelist)

    @staticmethod
    def _validate_dynamic_whitelist(action: Any, tool_whitelist: Any | None) -> None:
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
