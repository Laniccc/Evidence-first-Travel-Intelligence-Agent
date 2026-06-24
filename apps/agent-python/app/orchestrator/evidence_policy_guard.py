from app.config import get_settings
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.comparison_helpers import comparison_max_tool_calls, is_comparison_mode
from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.policy_guard import PolicyGuard
from app.orchestrator.state_policy import StateNodePolicy
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.semantic_frame import AnswerMode
from app.schemas.tool_whitelist import ToolWhitelist
from app.schemas.user_query import TravelAgentState
from app.orchestrator.tool_whitelist_builder import location_usage_allowed
from app.tools.mcp.adapter_status import is_mcp_policy_placeholder
from app.tools.mcp.client_manager import get_mcp_client_manager
from app.tools.mcp.tool_specs import MCP_POLICY_SPECS, NEED_TOOL_PROFILES
from app.tools.tool_name_resolver import is_mcp_policy_tool, resolve_tool_name
from tools.ticketing.provider_config import (
    is_crowd_provider_tool,
    is_ticket_provider_tool,
    provider_configured_for_tool,
    provider_enabled_for_tool,
)
_HARD_FACT_CLAIMS = frozenset(
    {
        "opening_hours",
        "ticket_price",
        "seasonal_operation_status",
        "road_opening_period",
        "temporary_closure",
        "reservation_policy",
        "reservation_required",
        "current_weather",
        "today_weather",
        "forecast",
        "current_crowd",
        "queue_time",
    }
)

_HARD_FACT_NEEDS = _HARD_FACT_CLAIMS

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

        gap_mode = state.current_evidence_gap_request is not None

        if action.action_type == AgentActionType.CALL_TOOL:
            self._validate_max_tool_calls(tool_call_count, gap_mode=gap_mode, state=state)
            self._validate_tool_call(action, state, tool_whitelist)

        if action.action_type == AgentActionType.CALL_SUBAGENT:
            self._validate_subagent_call(action, state, tool_whitelist)

        if action.action_type == AgentActionType.FINISH_STATE:
            if state.current_evidence_gap_request is not None:
                return
            self._validate_finish(action, state, tool_whitelist)

    @staticmethod
    def _validate_max_tool_calls(
        tool_call_count: int,
        *,
        gap_mode: bool = False,
        state: TravelAgentState | None = None,
    ) -> None:
        settings = get_settings()
        if gap_mode:
            limit = settings.evidence_gap_max_extra_steps
        elif state and is_comparison_mode(state):
            limit = comparison_max_tool_calls()
        else:
            limit = settings.mcp_max_tool_calls_per_state
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
        resolved = resolve_tool_name(tool)

        if is_mcp_policy_placeholder(resolved):
            raise ValueError(f"not_implemented: MCP policy tool {tool!r} is a placeholder (provider not wired)")

        if is_ticket_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                raise ValueError(f"disabled_by_config: ticket provider {tool!r}")
            if not provider_configured_for_tool(resolved, settings):
                if resolved in {"ticketlens_experience_mcp", "ticketlens_experience_review_signal_mcp"}:
                    if not settings.ticketlens_api_key:
                        raise ValueError(f"missing_api_key: TicketLens API key required for {tool!r}")
                raise ValueError(f"not_configured: ticket provider {tool!r}")
            if tool_whitelist and not tool_whitelist.is_allowed(tool) and not tool_whitelist.is_allowed(resolved):
                reason = tool_whitelist.reason_by_tool.get(tool, f"ticket provider {tool} blocked")
                raise ValueError(reason)
            return

        if is_crowd_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                raise ValueError(f"disabled_by_config: crowd provider {tool!r}")
            if not provider_configured_for_tool(resolved, settings):
                raise ValueError(f"not_configured: crowd provider {tool!r}")
            if tool_whitelist and not tool_whitelist.is_allowed(tool) and not tool_whitelist.is_allowed(resolved):
                reason = tool_whitelist.reason_by_tool.get(tool, f"crowd provider {tool} blocked")
                raise ValueError(reason)
            return

        if state.s5_domain_plan and tool in state.s5_domain_plan.effective_forbidden_tool_names():
            raise ValueError(f"forbidden_by_claim_policy: tool {tool!r} is forbidden for current S5 domain plan")

        if action.arguments.get("single_review_override"):
            raise ValueError(
                "review_signal evidence must be aggregated; single_review_override is not allowed"
            )

        if tool == "baidu_ip_location_mcp":
            if not location_usage_allowed(state):
                raise ValueError(
                    "baidu_ip_location_mcp requires location_usage_allowed or explicit nearby-me query"
                )

        if tool == "knowledge_prior":
            need = (
                action.arguments.get("information_need")
                or action.arguments.get("need_type")
                or self._primary_need(state)
            )
            contract = state.response_contract
            if contract:
                if not any(c.model_prior_allowed for c in contract.claim_requirements):
                    raise ValueError("ResponseContract: knowledge_prior not allowed for any claim")
                hard_required = [
                    c.claim_type
                    for c in contract.claim_requirements
                    if c.priority == "required" and c.claim_type in _HARD_FACT_CLAIMS
                ]
                if hard_required:
                    raise ValueError(
                        "knowledge_prior cannot satisfy required hard-fact claims: "
                        + ", ".join(hard_required)
                    )
                if need:
                    matching = [c for c in contract.claim_requirements if c.claim_type == need]
                    if matching and not any(c.model_prior_allowed for c in matching):
                        raise ValueError(
                            f"knowledge_prior not allowed for claim {need!r} per ResponseContract"
                        )
            elif need in _HARD_FACT_NEEDS or need in _HARD_FACT_CLAIMS or need in EvidencePolicy.forbidden_model_prior_claims():
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

    def _validate_subagent_call(
        self,
        action: AgentAction,
        state: TravelAgentState,
        tool_whitelist: ToolWhitelist | None,
    ) -> None:
        target = action.target or ""
        if target == "keyword_search_agent":
            from app.agents.keyword_search_agent import KeywordSearchAgent
            from app.schemas.search_task import SearchTask

            args = action.arguments or {}
            task = SearchTask.model_validate(
                {
                    "task_id": args.get("task_id") or "keyword-search",
                    "anchor_keywords": args.get("anchor_keywords") or [],
                    "search_query": args.get("search_query") or args.get("query") or "",
                    "information_need": args.get("information_need") or self._primary_need(state),
                    "preferred_tool": args.get("preferred_tool") or "search_mcp",
                }
            )
            KeywordSearchAgent.validate_task(task)
            tool = resolve_tool_name(task.preferred_tool)
            if tool_whitelist and not tool_whitelist.is_allowed(tool):
                raise ValueError(f"keyword_search_agent tool {tool!r} not in whitelist")
        elif target == "search_task_planner_agent":
            return
        elif target == "evidence_contradiction_decomposer_agent":
            return
        else:
            raise ValueError(f"Subagent {target!r} not allowed in evidence_planning_and_tool_use")

    def _validate_finish(
        self,
        action: AgentAction,
        state: TravelAgentState,
        tool_whitelist: ToolWhitelist | None = None,
    ) -> None:
        if action.arguments.get("evidence_gap_acknowledged"):
            return

        contract = state.response_contract
        if contract:
            checker = EvidenceCoverageChecker()
            report = state.coverage_report or checker.check(
                contract, state.evidence, state.tool_traces
            )
            if not report.can_finish_evidence_planning:
                untried = checker._untried_preferred_tools(contract, state.tool_traces)
                configured_untried = [
                    t for t in untried if tool_whitelist and tool_whitelist.is_allowed(t)
                ]
                if configured_untried:
                    raise ValueError(
                        "Cannot FINISH evidence planning: configured tools not yet attempted: "
                        + ", ".join(configured_untried)
                    )
            if not report.all_required_covered:
                missing = [
                    i.claim_type for i in report.items if not i.covered
                    if any(
                        c.claim_type == i.claim_type and c.priority == "required"
                        for c in contract.claim_requirements
                    )
                ]
                if missing:
                    raise ValueError(
                        "Cannot FINISH evidence planning without required claim coverage for: "
                        + ", ".join(missing)
                        + "; set evidence_gap_acknowledged=true with a limitation if tools failed"
                    )
            return

        decision = state.answer_mode_decision
        if not decision or decision.answer_mode != AnswerMode.EVIDENCE_REQUIRED:
            return

        frame = state.semantic_frame
        if not frame:
            return

        missing = self._missing_required_needs(state, frame.information_needs)
        untried = self._unconfigured_or_untried_tools(state, frame.information_needs, tool_whitelist)
        if untried:
            raise ValueError(
                "Cannot FINISH evidence planning: configured tools not yet attempted: "
                + ", ".join(untried)
            )

        if missing:
            raise ValueError(
                "Cannot FINISH evidence planning without required evidence for: "
                + ", ".join(missing)
                + "; set evidence_gap_acknowledged=true with a limitation if tools failed"
            )

    @staticmethod
    def _unconfigured_or_untried_tools(
        state: TravelAgentState,
        needs: list[str],
        tool_whitelist: ToolWhitelist | None,
    ) -> list[str]:
        if tool_whitelist is None:
            return []

        allowed = set(tool_whitelist.allowed_tool_names())
        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        pending: list[str] = []

        for need in needs:
            if need not in _HARD_FACT_NEEDS:
                continue
            profile = NEED_TOOL_PROFILES.get(need, [])
            for tool in profile:
                resolved = resolve_tool_name(tool)
                if tool in allowed and resolved not in called and tool not in pending:
                    pending.append(tool)
        return pending

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
