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

        if tool == "baidu_place_search_mcp":
            from app.orchestrator.ticket_lookup_policy import baidu_place_search_allowed_for_ticket

            if not baidu_place_search_allowed_for_ticket(state):
                raise ValueError(
                    "baidu_place_search_mcp not allowed after POI anchor for ticket_price; "
                    "use official/search/platform tools"
                )

        if is_mcp_policy_placeholder(resolved):
            raise ValueError(f"not_implemented: MCP policy tool {tool!r} is a placeholder (provider not wired)")

        args = dict(action.arguments or {})
        self._validate_tool_argument_requirements(resolved, args, state)

        if is_ticket_provider_tool(resolved):
            settings = get_settings()
            if not provider_enabled_for_tool(resolved, settings):
                raise ValueError(f"disabled_by_config: ticket provider {tool!r}")
            if not provider_configured_for_tool(resolved, settings):
                if resolved in {"ticketlens_experience_mcp", "ticketlens_experience_review_signal_mcp"}:
                    if not settings.ticketlens_api_key:
                        raise ValueError(f"missing_api_key: TicketLens API key required for {tool!r}")
                raise ValueError(f"not_configured: ticket provider {tool!r}")
            from app.orchestrator.ticket_lookup_policy import ticket_platform_tool_allowed, force_ticket_platform_phase

            if not ticket_platform_tool_allowed(state, resolved):
                if state.current_evidence_gap_request and state.current_evidence_gap_request.claim_type == "ticket_price":
                    force_ticket_platform_phase(state)
                if not ticket_platform_tool_allowed(state, resolved):
                    raise ValueError(
                        f"ticket platform tool {tool!r} not allowed in current lookup phase "
                        f"(use platform_ticket_candidate after entity anchor)"
                    )
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
        from app.agents.s5_subagent_registry import ORCHESTRATOR_SUBAGENT_NAMES
        from app.schemas.search_task import SearchTask

        target = action.target or ""
        from app.orchestrator.s5_poi_anchor_policy import blocks_subagent_until_poi_anchor

        if blocks_subagent_until_poi_anchor(state, target):
            raise ValueError(
                f"{target} blocked for nearby-style task until entity_resolution_agent anchors POI"
            )

        if target not in ORCHESTRATOR_SUBAGENT_NAMES and target not in {
            "search_task_planner_agent",
            "keyword_search_agent",
        }:
            raise ValueError(f"Subagent {target!r} not allowed in evidence_planning_and_tool_use")

        if target == "search_task_planner_agent":
            return
        if target == "evidence_contradiction_decomposer_agent":
            return

        args = action.arguments or {}
        need = str(args.get("information_need") or args.get("claim_target") or self._primary_need(state) or "unknown")
        task = SearchTask.model_validate(
            {
                "task_id": args.get("task_id") or f"{target}-task",
                "lookup_intent": args.get("lookup_intent") or args.get("rationale") or "",
                "claim_target": str(args.get("claim_target") or need),
                "anchor_keywords": args.get("anchor_keywords") or [],
                "search_query": args.get("search_query") or args.get("query") or "",
                "information_need": need,
                "preferred_tool": args.get("preferred_tool") or "search_mcp",
                "tool_parameters": args.get("tool_parameters") or {},
            }
        )

        if target in {"keyword_search_agent", "fact_search_agent"}:
            from app.agents.keyword_search_agent import KeywordSearchAgent

            KeywordSearchAgent.validate_task(task)
            tool = KeywordSearchAgent._preferred_tool_is_usable(task, tool_whitelist)
            if not tool:
                if target == "fact_search_agent":
                    from app.agents.fact_search_agent import FactSearchAgent

                    tool = FactSearchAgent.pick_tool(task, tool_whitelist, state=state)
                else:
                    tool = KeywordSearchAgent.pick_tool(task, tool_whitelist)
            if tool_whitelist and not tool_whitelist.is_allowed(tool):
                raise ValueError(f"{target} tool {tool!r} not in whitelist")
            return

        if target == "entity_resolution_agent":
            from app.orchestrator.lookup_entity_resolution_policy import entity_resolution_allowed_for_lookup

            if not entity_resolution_allowed_for_lookup(state):
                raise ValueError(
                    "entity_resolution_agent blocked: canonical place already anchored "
                    "or max entity_resolution calls reached for LOOKUP"
                )
            if not (task.search_query.strip() or task.anchor_keywords):
                raise ValueError("entity_resolution_agent requires search_query or anchor_keywords")
            if tool_whitelist and not tool_whitelist.is_allowed("baidu_place_search_mcp"):
                raise ValueError("entity_resolution_agent requires baidu_place_search_mcp in whitelist")
            return

        if target == "route_feasibility_agent":
            params = task.tool_parameters or {}
            if tool_whitelist and not any(
                tool_whitelist.is_allowed(t)
                for t in ("baidu_route_mcp", "baidu_traffic_mcp", "baidu_place_search_mcp")
            ):
                raise ValueError("route_feasibility_agent requires baidu route tools in whitelist")
            return

        if target == "weather_context_agent":
            if tool_whitelist and not any(
                tool_whitelist.is_allowed(t) for t in ("baidu_weather_mcp", "openmeteo_mcp", "weather_mcp")
            ):
                raise ValueError("weather_context_agent requires weather tools in whitelist")
            return

    def _validate_finish(
        self,
        action: AgentAction,
        state: TravelAgentState,
        tool_whitelist: ToolWhitelist | None = None,
    ) -> None:
        if action.arguments.get("evidence_gap_acknowledged"):
            return

        from app.orchestrator.retrieval_attempt_ledger import retrieval_complete, sync_ledger_to_state

        contract = state.response_contract
        if contract:
            required_claims = [
                c.claim_type
                for c in contract.claim_requirements
                if c.priority == "required"
            ]
            ledger_finish_claims = {"ticket_price", "opening_hours"} & set(required_claims)
            if ledger_finish_claims and all(
                retrieval_complete(state, ct) for ct in ledger_finish_claims
            ):
                sync_ledger_to_state(state)
                return

            checker = EvidenceCoverageChecker()
            report = state.coverage_report or checker.check(
                contract, state.evidence, state.tool_traces
            )
            if not report.all_required_covered:
                missing = [
                    i.claim_type
                    for i in report.items
                    if not i.covered
                    if any(
                        c.claim_type == i.claim_type and c.priority == "required"
                        for c in contract.claim_requirements
                    )
                ]
                if missing and all(retrieval_complete(state, m) for m in missing if m in ledger_finish_claims):
                    sync_ledger_to_state(state)
                    return
                if missing:
                    untried = self._untried_contract_tools(
                        state,
                        contract.claim_requirements,
                        tool_whitelist,
                        missing,
                    )
                    if untried:
                        raise ValueError(
                            "Cannot FINISH evidence planning: configured tools not yet attempted: "
                            + ", ".join(untried)
                        )
                    still_blocking = [
                        m
                        for m in missing
                        if m not in ledger_finish_claims or not retrieval_complete(state, m)
                    ]
                    if not still_blocking:
                        sync_ledger_to_state(state)
                        return
                    raise ValueError(
                        "Cannot FINISH evidence planning without required claim coverage for: "
                        + ", ".join(still_blocking)
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
        ledger_needs = {"ticket_price", "opening_hours"} & set(frame.information_needs or [])
        if ledger_needs and all(retrieval_complete(state, n) for n in ledger_needs):
            sync_ledger_to_state(state)
            return

        untried = self._unconfigured_or_untried_tools(state, frame.information_needs, tool_whitelist)
        if untried:
            raise ValueError(
                "Cannot FINISH evidence planning: configured tools not yet attempted: "
                + ", ".join(untried)
            )

        if missing:
            still_blocking = [
                m
                for m in missing
                if m not in ledger_needs or not retrieval_complete(state, m)
            ]
            if not still_blocking:
                sync_ledger_to_state(state)
                return
            raise ValueError(
                "Cannot FINISH evidence planning without required evidence for: "
                + ", ".join(still_blocking)
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
    def _untried_contract_tools(
        state: TravelAgentState,
        claims,
        tool_whitelist: ToolWhitelist | None,
        missing_claims: list[str],
    ) -> list[str]:
        if tool_whitelist is None:
            return []
        allowed = set(tool_whitelist.allowed_tool_names())
        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        missing_set = set(missing_claims)
        pending: list[str] = []
        for claim in claims:
            if claim.claim_type not in missing_set:
                continue
            if claim.priority != "required":
                continue
            for tool in claim.preferred_tools:
                resolved = resolve_tool_name(tool)
                if tool in allowed and resolved not in called and tool not in pending:
                    pending.append(tool)
        return pending

    @staticmethod
    def _validate_tool_argument_requirements(tool: str, args: dict, state: TravelAgentState) -> None:
        resolved = resolve_tool_name(tool)
        if resolved == "baidu_reverse_geocode_mcp":
            lat = args.get("latitude")
            lng = args.get("longitude")
            if lat is None or lng is None:
                raise ValueError("baidu_reverse_geocode_mcp requires latitude and longitude")
        if resolved == "baidu_place_detail_mcp":
            uid = str(args.get("uid") or "").strip()
            if uid:
                from tools.mcp.adapters.baidu_response_parser import is_valid_baidu_uid

                if not is_valid_baidu_uid(uid):
                    raise ValueError("baidu_place_detail_mcp uid must come from baidu place candidate.uid")
        if resolved == "official_source_discovery_mcp":
            from app.orchestrator.ticket_lookup_helpers import collect_ticket_search_urls, has_ticket_url_inputs

            urls = list(args.get("urls") or [])
            hits = list(args.get("search_results") or [])
            if not urls and not hits and not has_ticket_url_inputs(state):
                from app.orchestrator.fact_lookup_policy import primary_fact_need_from_state
                from app.orchestrator.retrieval_attempt_ledger import record_skip

                reason = "official_source_discovery_mcp requires urls or search_results; skip when none available"
                record_skip(state, "official_source", reason, claim_type=primary_fact_need_from_state(state))
                raise ValueError(reason)
        if resolved in {"official_page_reader_mcp", "browser_mcp"}:
            url = str(args.get("url") or args.get("source_url") or "").strip()
            urls = args.get("urls") or []
            if not url and not urls:
                from app.orchestrator.ticket_lookup_helpers import collect_ticket_search_urls

                if not collect_ticket_search_urls(state):
                    raise ValueError(f"{resolved} requires a readable url")

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
