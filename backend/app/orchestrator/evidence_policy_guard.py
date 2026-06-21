from app.config import get_settings
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.policy_guard import PolicyGuard
from app.orchestrator.state_policy import StateNodePolicy
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.semantic_frame import AnswerMode
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.tools.mcp.client_manager import get_mcp_client_manager
from app.tools.mcp.tool_specs import MCP_POLICY_SPECS
from app.tools.tool_name_resolver import is_mcp_policy_tool
_HARD_FACT_NEEDS = frozenset(
    {
        "opening_hours",
        "ticket_price",
        "weather_today",
        "today_weather",
        "current_crowd",
        "temporary_closure",
        "reservation_policy",
    }
)

_CLAIM_TYPE_TO_NEED: dict[str, str] = {
    ClaimType.OPENING_HOURS.value: "opening_hours",
    ClaimType.TICKET_PRICE.value: "ticket_price",
    ClaimType.WEATHER.value: "weather_today",
    ClaimType.CROWD.value: "current_crowd",
    ClaimType.RESERVATION.value: "reservation_policy",
}


class EvidencePolicyGuard(PolicyGuard):
    """Policy guard with EvidencePolicy rules for evidence planning loop."""

    def validate(
        self,
        action: AgentAction,
        policy: StateNodePolicy,
        state: TravelAgentState | None = None,
        tool_whitelist: ToolWhitelist | None = None,
        *,
        tool_call_count: int = 0,
    ) -> None:
        super().validate(action, policy, state, tool_whitelist)
        if policy.state_name != "evidence_planning_and_tool_use" or state is None:
            return

        if action.action_type == AgentActionType.CALL_TOOL:
            self._validate_max_tool_calls(tool_call_count)
            self._validate_tool_call(action, state, tool_whitelist)

        if action.action_type == AgentActionType.FINISH_STATE:
            self._validate_finish(action, state)

    @staticmethod
    def _validate_max_tool_calls(tool_call_count: int) -> None:
        limit = get_settings().mcp_max_tool_calls_per_state
        if tool_call_count >= limit:
            raise ValueError(
                f"S5 max tool calls ({limit}) reached; FINISH_STATE or UPDATE_STATE with limitations"
            )

    def _validate_tool_call(
        self,
        action: AgentAction,
        state: TravelAgentState,
        tool_whitelist: ToolWhitelist | None,
    ) -> None:
        tool = action.target or ""

        if tool == "knowledge_prior":
            need = (
                action.arguments.get("information_need")
                or action.arguments.get("need_type")
                or self._primary_need(state)
            )
            if need in _HARD_FACT_NEEDS or need in EvidencePolicy.forbidden_model_prior_claims():
                raise ValueError(
                    f"knowledge_prior cannot satisfy hard-fact need {need!r}; "
                    "use official/places/MCP tools from allowed_tools"
                )
            if need and not EvidencePolicy.model_prior_allowed_for(need):
                raise ValueError(f"knowledge_prior not allowed for information need {need!r}")
            if tool_whitelist and not tool_whitelist.is_allowed("knowledge_prior"):
                reason = tool_whitelist.reason_by_tool.get(
                    "knowledge_prior",
                    "knowledge_prior blocked by task whitelist",
                )
                raise ValueError(reason)
            return

        if is_mcp_policy_tool(tool):
            spec = MCP_POLICY_SPECS.get(tool)
            if spec is None and tool == "official_mcp":
                spec = MCP_POLICY_SPECS.get("official_page_reader_mcp")
            if spec is None:
                raise ValueError(f"Unknown MCP policy tool {tool!r}")
            server_name = spec[0]
            if not get_mcp_client_manager().is_server_configured(server_name):
                raise ValueError(f"Unconfigured MCP tool {tool!r}: server {server_name} not available")
            if tool_whitelist and not tool_whitelist.is_allowed(tool):
                reason = tool_whitelist.reason_by_tool.get(tool, f"MCP {tool} blocked")
                raise ValueError(reason)

    def _validate_finish(self, action: AgentAction, state: TravelAgentState) -> None:
        decision = state.answer_mode_decision
        if not decision or decision.answer_mode != AnswerMode.EVIDENCE_REQUIRED:
            return

        if action.arguments.get("evidence_gap_acknowledged"):
            return

        frame = state.semantic_frame
        if not frame:
            return

        missing = self._missing_required_needs(state, frame.information_needs)
        if missing:
            raise ValueError(
                "Cannot FINISH evidence planning without required evidence for: "
                + ", ".join(missing)
                + "; set evidence_gap_acknowledged=true with a limitation if tools failed"
            )

    @staticmethod
    def _primary_need(state: TravelAgentState) -> str | None:
        frame = state.semantic_frame
        if frame and frame.information_needs:
            return frame.information_needs[0]
        if state.information_needs:
            return state.information_needs[0].need_type.value
        return None

    @staticmethod
    def _missing_required_needs(state: TravelAgentState, needs: list[str]) -> list[str]:
        covered: set[str] = set()
        for ev in state.evidence:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims:
                need = _CLAIM_TYPE_TO_NEED.get(claim.claim_type.value)
                if need:
                    covered.add(need)
                if claim.claim_type.value in needs:
                    covered.add(claim.claim_type.value)

        missing: list[str] = []
        for need in needs:
            if need in _HARD_FACT_NEEDS and need not in covered:
                if EvidencePolicy.requires_evidence_for(need):
                    missing.append(need)
        return missing
