import json

from app.agents.information_need_planner import InformationNeedPlanner
from app.llm_client import LLMClient
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.state_policy import StateNodePolicy
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.semantic_frame import AnswerMode, DecisionType
from app.schemas.user_query import TravelAgentState
from app.tools.mcp.tool_specs import NEED_TOOL_PROFILES
from app.tools.tool_name_resolver import resolve_tool_name
from app.schemas.s5_information_domain import InformationDomain, ProviderGroup, S5ToolRole
from tools.ticketing.provider_config import is_ticket_provider_tool


class ActionModelController:
    """Propose the next structured action — LLM when available, else deterministic plan."""

    _HARD_FACT_NEEDS = frozenset(
        {
            "opening_hours",
            "ticket_price",
            "ticket_price_candidate",
            "weather_today",
            "today_weather",
            "forecast",
            "current_crowd",
            "queue_time",
            "temporary_closure",
            "reservation_policy",
        }
    )

    def __init__(self, llm_client=None) -> None:
        self.llm = llm_client or LLMClient()

    async def next_action(
        self,
        state: TravelAgentState,
        policy: StateNodePolicy,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        # Answer composition has a fixed two-step plan; LLM routing here can skip
        # composer_agent and FINISH with an empty result (→ blank API answer).
        if policy.state_name == "answer_composition":
            prompt_context["_last_action_source"] = "deterministic"
            return self._deterministic_action(state, policy, prompt_context, step)
        if policy.state_name == "evidence_aggregation":
            prompt_context["_last_action_source"] = "deterministic"
            return self._deterministic_action(state, policy, prompt_context, step)
        if policy.state_name == "evidence_planning_and_tool_use":
            if prompt_context.get("gap_filling"):
                prompt_context["_last_action_source"] = "deterministic_gap"
                return self._deterministic_action(state, policy, prompt_context, step)
            if self._hard_fact_interleave_due(state, prompt_context):
                prompt_context["_last_action_source"] = "hard_fact_interleave"
                return self._hard_fact_interleave_action(state, prompt_context)
            if self._contradiction_decompose_due(state, prompt_context):
                prompt_context["_last_action_source"] = "contradiction_decompose"
                return self._contradiction_decompose_action(state, prompt_context)
            if self._search_strategy_review_due(state, prompt_context):
                prompt_context["_last_action_source"] = "search_strategy_review"
                return await self._search_strategy_review_action(state, prompt_context)
            # S5 routing is deterministic; LLM is used only inside search_task_planner_agent.
            prompt_context["_last_action_source"] = "deterministic"
            return self._deterministic_action(state, policy, prompt_context, step)
        if self.llm and self.llm._should_use_anthropic():
            try:
                action = await self._llm_action(state, policy, prompt_context, step)
                prompt_context["_last_action_source"] = "llm"
                return action
            except Exception:
                pass
        prompt_context["_last_action_source"] = "deterministic"
        return self._deterministic_action(state, policy, prompt_context, step)

    async def _llm_action(
        self,
        state: TravelAgentState,
        policy: StateNodePolicy,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        system = (
            "You are a state-loop controller. Return ONLY valid JSON for one AgentAction.\n"
            f"state_name={policy.state_name}\n"
            f"allowed_actions={[a.value for a in policy.allowed_actions]}\n"
            f"allowed_subagents={policy.allowed_subagents}\n"
            f"max_steps={policy.max_steps}, current_step={step + 1}\n"
            "Schema: {action_type, target, arguments, reason_summary, confidence}"
        )
        if policy.state_name == "evidence_planning_and_tool_use":
            rules = prompt_context.get("s5_prompt_rules", [])
            allowed = prompt_context.get("allowed_tools", [])
            subagents = policy.allowed_subagents
            system += (
                "\n\nS5 Evidence Planning rules:\n"
                + "\n".join(f"- {rule}" for rule in rules)
                + f"\nallowed_tools (CALL_TOOL targets): {[t.get('name') for t in allowed]}\n"
                + f"allowed_subagents (CALL_SUBAGENT targets): {subagents}\n"
                "Primary path: CALL_SUBAGENT search_task_planner_agent or keyword_search_agent.\n"
                "keyword_search_agent arguments MUST include: anchor_keywords (from S4), search_query, "
                "information_need (search purpose for this lookup). preferred_tool is optional hint only.\n"
                "When evidence contains place_candidates (多地同名), refine search_query with region/city "
                "in the next keyword_search tasks — do NOT ask the user in S5.\n"
                "Every 2 keyword_search_agent completions trigger search_task_planner refine automatically.\n"
                "CALL_TOOL only when subagents cannot cover (e.g. one-off geo); avoid bypassing subagents.\n"
                "Never output final answer text."
            )
        else:
            system += f"\nallowed_tools={policy.allowed_tools}\n"
        user_payload = {
            "raw_query": state.raw_user_query,
            "step": step,
            "has_query_understanding": state.query_understanding is not None,
            "has_semantic_frame": state.semantic_frame is not None,
            "has_final_response": bool(state.final_response),
            "prompt_context_keys": list(prompt_context.keys()),
            "compose_mode": prompt_context.get("compose_mode"),
        }
        if policy.state_name == "evidence_planning_and_tool_use":
            frame = state.semantic_frame
            decision = state.answer_mode_decision
            whitelist = prompt_context.get("tool_whitelist")
            user_payload.update(
                {
                    "semantic_frame": frame.model_dump() if frame else None,
                    "answer_mode": decision.answer_mode.value if decision else None,
                    "allow_knowledge_prior": bool(decision and decision.allow_knowledge_prior),
                    "information_needs": [n.model_dump() for n in state.information_needs],
                    "evidence_count": len(state.evidence),
                    "tools_called": [t.tool_name for t in state.tool_traces],
                    "allowed_tools": prompt_context.get("allowed_tools", []),
                    "blocked_tools": prompt_context.get("blocked_tools", []),
                    "whitelist_policy_notes": prompt_context.get("whitelist_policy_notes", []),
                    "s5_prompt_rules": prompt_context.get("s5_prompt_rules", []),
                    "search_tasks": self._search_tasks_from_state(state),
                    "completed_search_task_ids": self._completed_search_task_ids(state),
                    "tool_diversity_hints": prompt_context.get("tool_diversity_hints", []),
                    "planning_context": ClaimSearchPlanner.planning_context(state),
                    "keyword_search_count": ClaimSearchPlanner.keyword_search_call_count(state),
                    "max_keyword_searches": ClaimSearchPlanner.max_search_attempts(state),
                }
            )
            if whitelist is not None:
                user_payload["allowed_tool_names"] = whitelist.allowed_tool_names()
        user = json.dumps(user_payload, ensure_ascii=False, default=str)
        raw = await self.llm.complete(system=system, user=user, max_tokens=400)
        data = json.loads(raw)
        return AgentAction.model_validate(data)

    def _deterministic_action(
        self,
        state: TravelAgentState,
        policy: StateNodePolicy,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        if policy.state_name == "query_understanding":
            return self._plan_query_understanding(state, step)
        if policy.state_name == "answer_composition":
            return self._plan_answer_composition(state, prompt_context, step)
        if policy.state_name == "evidence_planning_and_tool_use":
            if prompt_context.get("gap_filling"):
                return self._plan_gap_filling(state, prompt_context, step)
            return self._plan_evidence_planning_and_tool_use(state, prompt_context, step)
        if policy.state_name == "evidence_aggregation":
            return self._plan_evidence_aggregation(state, prompt_context, step)
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            reason_summary=f"Unknown policy {policy.state_name}",
        )

    def _plan_query_understanding(self, state: TravelAgentState, step: int) -> AgentAction:
        if state.query_understanding is None:
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="query_understanding",
                reason_summary="Phase-1: delegate to QueryUnderstandingAgent",
                confidence=0.9,
                expected_output_schema="QueryUnderstandingResult",
            )
        qu = state.query_understanding
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments={"result": qu.model_dump()},
            expected_output_schema="QueryUnderstandingResult",
            reason_summary="QueryUnderstanding complete",
            confidence=qu.confidence,
        )

    def _plan_answer_composition(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        from app.orchestrator.composition_preflight import should_compose_over_clarification

        draft_data = (state.structured_result or {}).get("final_answer_draft")
        if draft_data is None and state.final_response:
            if should_compose_over_clarification(state):
                state.final_response = ""
            else:
                draft_data = {
                    "answer_text": state.final_response,
                    "conclusion": state.final_response[:200],
                    "compose_mode": prompt_context.get("compose_mode", "advisory"),
                }
        if draft_data is None and not state.final_response:
            args = {k: v for k, v in prompt_context.items() if k != "user_ctx"}
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="composer_agent",
                arguments=args,
                reason_summary=f"Phase-1: compose via AnswerComposerAgent ({prompt_context.get('compose_mode', 'advisory')})",
                confidence=0.85,
                expected_output_schema="FinalAnswerDraft",
            )
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments={"result": draft_data},
            expected_output_schema="FinalAnswerDraft",
            reason_summary="Answer composition complete",
            confidence=0.85,
        )

    def _plan_evidence_planning_and_tool_use(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        if step == 0 and not state.information_needs and state.travel_task:
            needs = InformationNeedPlanner.plan(state.travel_task)
            notes = ["Initialized information_needs from planner candidate (LLM may revise)."]
            return AgentAction(
                action_type=AgentActionType.UPDATE_STATE,
                arguments={
                    "information_needs": [n.model_dump() for n in needs],
                    "planning_notes": notes,
                },
                reason_summary="Seed information_needs for evidence planning loop",
                confidence=0.8,
            )

        allowed_names = set(self._whitelist_names(prompt_context))
        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        called |= {resolve_tool_name(t) for t in prompt_context.get("_called_policy_tools", [])}

        pending_task = self._next_pending_search_task(state)

        if not self._search_tasks_from_state(state):
            if not prompt_context.get("_search_task_planner_called"):
                prompt_context["_search_task_planner_called"] = True
                return AgentAction(
                    action_type=AgentActionType.CALL_SUBAGENT,
                    target="search_task_planner_agent",
                    arguments={},
                    reason_summary="A2A: LLM plans keyword search tasks from user query",
                    confidence=0.85,
                )

        if pending_task:
            kw_cap = self._max_keyword_searches_before_tools(state)
            if ClaimSearchPlanner.keyword_search_call_count(state) < kw_cap:
                return AgentAction(
                    action_type=AgentActionType.CALL_SUBAGENT,
                    target="keyword_search_agent",
                    arguments=pending_task,
                    reason_summary=f"A2A keyword search: {pending_task.get('search_query', '')[:56]}",
                    confidence=0.8,
                )

        if self._hard_fact_interleave_due(state, prompt_context):
            return self._hard_fact_interleave_action(state, prompt_context)

        if (
            self._search_tasks_from_state(state)
            and "search_mcp" in allowed_names
            and ClaimSearchPlanner.searches_failed(state)
            and not prompt_context.get("_search_refine_planned")
            and ClaimSearchPlanner.search_call_count(state) < ClaimSearchPlanner.max_search_attempts(state)
        ):
            prompt_context["_search_refine_planned"] = True
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="search_task_planner_agent",
                arguments={"refine": True},
                reason_summary="A2A: LLM refines keyword search tasks after misses",
                confidence=0.8,
            )

        prior_args = self._optional_prior_arguments(state, prompt_context, allowed_names, called)
        if prior_args:
            search_done = self._search_call_count(state)
            min_searches = min(2, ClaimSearchPlanner.max_search_attempts(state))
            if search_done < min_searches:
                prior_args = None
        if prior_args:
            prompt_context.setdefault("_called_policy_tools", []).append("knowledge_prior")
            return AgentAction(
                action_type=AgentActionType.CALL_TOOL,
                target="knowledge_prior",
                arguments=prior_args,
                reason_summary="Low-confidence general seasonal context (optional claim)",
                confidence=0.55,
            )

        queue = self._evidence_tool_queue(state, prompt_context)
        if allowed_names:
            queue = [tool for tool in queue if tool in allowed_names]
        next_tool = next((tool for tool in queue if resolve_tool_name(tool) not in called), None)
        if next_tool in {"openmeteo_mcp", "climate_mcp"} and self._needs_coordinate_resolution(state):
            if "baidu_geocode_mcp" in allowed_names and resolve_tool_name("baidu_geocode_mcp") not in called:
                next_tool = "baidu_geocode_mcp"
        if next_tool:
            return self._make_call_tool_action(
                next_tool,
                state,
                prompt_context,
                reason_summary=f"Retrieve evidence via {next_tool}",
            )

        finish_args: dict = {}
        contract = state.response_contract
        if contract:
            from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker

            report = state.coverage_report or EvidenceCoverageChecker().check(
                contract, state.evidence, state.tool_traces
            )
            if not report.all_required_covered:
                tried = [t.tool_name for t in state.tool_traces]
                missing = [
                    i.claim_type
                    for i in report.items
                    if not i.covered
                    and any(
                        c.claim_type == i.claim_type and c.priority == "required"
                        for c in contract.claim_requirements
                    )
                ]
                finish_args["evidence_gap_acknowledged"] = True
                finish_args["limitations"] = [
                    "已尝试 "
                    + (", ".join(tried) if tried else "（无）")
                    + "，但未获取到可验证 "
                    + "/".join(missing)
                    + " 证据。"
                ]
        else:
            decision = state.answer_mode_decision
            frame = state.semantic_frame
            if decision and decision.answer_mode == AnswerMode.EVIDENCE_REQUIRED:
                missing_needs: list[str] = []
                if frame:
                    from app.orchestrator.evidence_policy_guard import EvidencePolicyGuard

                    guard = EvidencePolicyGuard()
                    missing_needs = guard._missing_required_needs(state, frame.information_needs)
                if missing_needs or not state.evidence:
                    tried = [t.tool_name for t in state.tool_traces]
                    finish_args["evidence_gap_acknowledged"] = True
                    finish_args["limitations"] = [
                        "已尝试 "
                        + (", ".join(tried) if tried else "（无）")
                        + "，但未获取到可验证"
                        + (" " + "/".join(missing_needs) if missing_needs else "")
                        + " 证据；强事实问题不能用模型常识补全。"
                    ]
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments=finish_args,
            reason_summary="Evidence sufficient or tool queue exhausted",
            confidence=0.8,
        )

    def _make_call_tool_action(
        self,
        tool: str,
        state: TravelAgentState,
        prompt_context: dict,
        *,
        reason_summary: str,
        confidence: float = 0.75,
        extra_arguments: dict | None = None,
    ) -> AgentAction:
        prompt_context.setdefault("_called_policy_tools", []).append(tool)
        args = self._tool_arguments_for(tool, state, prompt_context)
        if extra_arguments:
            args.update(extra_arguments)
        return AgentAction(
            action_type=AgentActionType.CALL_TOOL,
            target=tool,
            arguments=args,
            reason_summary=reason_summary,
            confidence=confidence,
        )

    def _pop_tool_batch_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> AgentAction | None:
        queue: list[dict] = list(prompt_context.get("_tool_batch_queue") or [])
        if not queue:
            return None
        item = queue.pop(0)
        prompt_context["_tool_batch_queue"] = queue
        target = item.get("target") or ""
        if not target:
            return self._pop_tool_batch_action(state, prompt_context)
        return self._make_call_tool_action(
            target,
            state,
            prompt_context,
            reason_summary=item.get("reason_summary") or f"S5 planned tool: {target}",
            extra_arguments=item.get("arguments"),
        )

    @staticmethod
    def _searches_since_review(state: TravelAgentState, prompt_context: dict) -> int:
        baseline = int(prompt_context.get("_last_review_search_count", 0))
        return ClaimSearchPlanner.search_call_count(state) - baseline

    def _has_hard_fact_needs(self, state: TravelAgentState) -> bool:
        return bool(self._HARD_FACT_NEEDS & set(self._merged_information_needs(state)))

    def _max_keyword_searches_before_tools(self, state: TravelAgentState) -> int:
        if self._has_hard_fact_needs(state):
            return min(4, ClaimSearchPlanner.max_search_attempts(state))
        return ClaimSearchPlanner.max_search_attempts(state)

    def _pending_hard_fact_tools(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> list[str]:
        allowed = set(self._whitelist_names(prompt_context))
        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        called |= {resolve_tool_name(t) for t in prompt_context.get("_called_policy_tools", [])}
        callable_set = set(
            self._callable_non_search_queue(state, prompt_context, allowed)
        )
        ordered: list[str] = []
        for need in self._merged_information_needs(state):
            if need not in self._HARD_FACT_NEEDS:
                continue
            for tool in NEED_TOOL_PROFILES.get(need, []):
                resolved = resolve_tool_name(tool)
                if resolved in allowed and resolved in callable_set and resolved not in called:
                    if resolved not in ordered:
                        ordered.append(resolved)
        return ordered

    def _hard_fact_interleave_due(self, state: TravelAgentState, prompt_context: dict) -> bool:
        if not self._has_hard_fact_needs(state):
            return False
        count = ClaimSearchPlanner.keyword_search_call_count(state)
        if count < 2:
            return False
        baseline = int(prompt_context.get("_last_interleave_keyword_count", 0))
        if count - baseline < 2:
            return False
        return bool(self._pending_hard_fact_tools(state, prompt_context))

    def _hard_fact_interleave_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> AgentAction:
        prompt_context["_last_interleave_keyword_count"] = ClaimSearchPlanner.keyword_search_call_count(
            state
        )
        next_tool = self._pending_hard_fact_tools(state, prompt_context)[0]
        return self._make_call_tool_action(
            next_tool,
            state,
            prompt_context,
            reason_summary=f"S5 hard-fact interleave after keyword searches: {next_tool}",
            confidence=0.82,
        )

    def _search_strategy_review_due(self, state: TravelAgentState, prompt_context: dict) -> bool:
        count = ClaimSearchPlanner.keyword_search_call_count(state)
        if count < 2:
            return False
        baseline = int(prompt_context.get("_last_review_keyword_count", 0))
        if count - baseline < 2:
            return False
        if int(prompt_context.get("_review_round", 0)) >= 2:
            return False
        if count >= self._max_keyword_searches_before_tools(state):
            return False
        if count >= ClaimSearchPlanner.max_search_attempts(state):
            return False
        if self._has_hard_fact_needs(state) and self._pending_hard_fact_tools(state, prompt_context):
            return False
        return True

    def _contradiction_decompose_due(self, state: TravelAgentState, prompt_context: dict) -> bool:
        from app.orchestrator.evidence_signal_utils import multi_value_signal_for_need

        if int(prompt_context.get("_contradiction_decompose_round", 0)) >= 2:
            return False
        primary = ClaimSearchPlanner.primary_information_need(state)
        if primary not in {"ticket_price", "opening_hours"}:
            return False
        kw = ClaimSearchPlanner.keyword_search_call_count(state)
        if kw < 2 and len(state.evidence) < 4:
            return False
        structured = state.structured_result or {}
        if structured.get("fact_decomposition") and structured.get("_decompose_evidence_count") == len(
            state.evidence
        ):
            return False
        return multi_value_signal_for_need(state, primary)

    def _contradiction_decompose_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> AgentAction:
        prompt_context["_contradiction_decompose_round"] = (
            int(prompt_context.get("_contradiction_decompose_round", 0)) + 1
        )
        return AgentAction(
            action_type=AgentActionType.CALL_SUBAGENT,
            target="evidence_contradiction_decomposer_agent",
            arguments={},
            reason_summary=(
                "S5 多源数值分歧：查证票种/套餐口径并分拆呈现，避免笼统称价格不确定"
            ),
            confidence=0.9,
        )

    async def _search_strategy_review_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> AgentAction:
        prompt_context["_last_review_keyword_count"] = ClaimSearchPlanner.keyword_search_call_count(state)
        prompt_context["_review_round"] = int(prompt_context.get("_review_round", 0)) + 1
        return AgentAction(
            action_type=AgentActionType.CALL_SUBAGENT,
            target="search_task_planner_agent",
            arguments={"refine": True},
            reason_summary=(
                "S5 每 2 次 keyword_search 后：结合 S4 关键词与子代理结果，"
                "调整下一批 search_query / information_need"
            ),
            confidence=0.88,
        )

    def _tool_review_checkpoint_due(self, state: TravelAgentState, prompt_context: dict) -> bool:
        if prompt_context.get("_tool_batch_queue"):
            return False
        if ClaimSearchPlanner.search_call_count(state) < 2:
            return False
        if self._searches_since_review(state, prompt_context) < 2:
            return False
        from app.config import get_settings

        max_calls = int(
            prompt_context.get("max_tool_calls") or get_settings().mcp_max_tool_calls_per_state
        )
        if int(prompt_context.get("tool_call_count", 0)) >= max_calls:
            return False
        return True

    def _apply_deterministic_review_batch(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> None:
        allowed = set(self._whitelist_names(prompt_context))
        batch = self._deterministic_batch_plan(state, prompt_context, allowed, count=2)
        prompt_context["_tool_batch_queue"] = batch
        prompt_context["_last_review_search_count"] = ClaimSearchPlanner.search_call_count(state)
        prompt_context["_review_round"] = int(prompt_context.get("_review_round", 0)) + 1

    def _deterministic_batch_plan(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        allowed_names: set[str],
        *,
        count: int = 2,
    ) -> list[dict]:
        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        called |= {resolve_tool_name(t) for t in prompt_context.get("_called_policy_tools", [])}
        queue = self._callable_non_search_queue(state, prompt_context, allowed_names)
        picks = [t for t in queue if resolve_tool_name(t) not in called][:count]
        return [
            {
                "target": tool,
                "arguments": {},
                "reason_summary": f"Deterministic review pick: {tool}",
            }
            for tool in picks
        ]

    async def _llm_tool_review_action(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> AgentAction:
        from app.config import get_settings
        from app.utils.llm_json import parse_llm_json

        allowed = set(self._whitelist_names(prompt_context))
        system = (
            "You review travel evidence gathering after every 2 keyword searches.\n"
            "Return ONLY valid JSON:\n"
            '{"review_summary":"...", "next_actions":[{"action_type":"call_tool",'
            '"target":"tool_name","arguments":{},"reason_summary":"..."}], '
            '"finish_recommended": false}\n'
            "Rules:\n"
            "- Propose 1-2 CALL_TOOL actions from allowed_tool_names only.\n"
            "- Review evidence_summary and recent search results; pick tools that cover missing information_needs.\n"
            "- Prefer differentiated tools (official/ticket/baidu/map) over repeating search_mcp if searches failed.\n"
            "- If required evidence is already sufficient, set finish_recommended=true and next_actions=[].\n"
            "- Do not output final user-facing answer text."
        )
        payload = {
            "raw_query": state.raw_user_query,
            "information_needs": self._merged_information_needs(state),
            "allowed_tool_names": sorted(allowed),
            "tools_called": [t.tool_name for t in state.tool_traces],
            "evidence_summary": self._evidence_summary_for_review(state),
            "searches_since_last_review": self._searches_since_review(state, prompt_context),
            "tool_call_count": prompt_context.get("tool_call_count", 0),
            "max_tool_calls": prompt_context.get("max_tool_calls")
            or get_settings().mcp_max_tool_calls_per_state,
            "tool_diversity_hints": prompt_context.get("tool_diversity_hints", []),
        }
        raw = await self.llm.complete(
            system=system,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            max_tokens=1200,
            json_only=True,
        )
        data = parse_llm_json(raw)
        if data.get("finish_recommended"):
            prompt_context["_last_review_search_count"] = ClaimSearchPlanner.search_call_count(state)
            prompt_context["_review_round"] = int(prompt_context.get("_review_round", 0)) + 1
            return AgentAction(
                action_type=AgentActionType.FINISH_STATE,
                arguments={
                    "limitations": [
                        str(data.get("review_summary") or "LLM review: evidence sufficient to finish S5.")
                    ]
                },
                reason_summary="LLM review recommends finishing evidence planning",
                confidence=0.75,
            )

        batch: list[dict] = []
        for item in data.get("next_actions") or []:
            if not isinstance(item, dict):
                continue
            target = item.get("target") or ""
            if target not in allowed:
                continue
            batch.append(
                {
                    "target": target,
                    "arguments": item.get("arguments") if isinstance(item.get("arguments"), dict) else {},
                    "reason_summary": item.get("reason_summary") or f"LLM review: {target}",
                }
            )
            if len(batch) >= 2:
                break
        if not batch:
            self._apply_deterministic_review_batch(state, prompt_context)
        else:
            prompt_context["_tool_batch_queue"] = batch
            prompt_context["_last_review_search_count"] = ClaimSearchPlanner.search_call_count(state)
            prompt_context["_review_round"] = int(prompt_context.get("_review_round", 0)) + 1

        popped = self._pop_tool_batch_action(state, prompt_context)
        if popped is not None:
            return popped
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments={"limitations": ["LLM review produced no executable tool batch."]},
            reason_summary="Review checkpoint produced empty tool batch",
            confidence=0.5,
        )

    @staticmethod
    def _evidence_summary_for_review(state: TravelAgentState) -> list[dict]:
        from app.schemas.evidence import Evidence

        rows: list[dict] = []
        for ev in state.evidence:
            if not isinstance(ev, Evidence):
                continue
            rows.append(
                {
                    "source_name": ev.source_name,
                    "place_name": ev.place_name,
                    "confidence": ev.confidence,
                    "claims": [
                        {
                            "type": c.claim_type.value,
                            "value": str(c.value)[:120],
                            "confidence": c.confidence,
                        }
                        for c in ev.claims[:4]
                    ],
                }
            )
        return rows[:12]

    @staticmethod
    def _merged_information_needs(state: TravelAgentState) -> list[str]:
        needs: list[str] = []
        frame = state.semantic_frame
        if frame and frame.information_needs:
            needs.extend(frame.information_needs)
        if state.information_needs:
            for n in state.information_needs:
                nt = n.need_type.value if hasattr(n.need_type, "value") else str(n.need_type)
                needs.append(nt)
        deduped: list[str] = []
        for need in needs:
            if need not in deduped:
                deduped.append(need)
        return deduped

    def _callable_non_search_queue(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        allowed_names: set[str],
    ) -> list[str]:
        from tools.mcp.adapters.baidu_response_parser import pick_baidu_uid_from_evidence

        queue = self._non_search_priority_queue(state, prompt_context, allowed_names)
        has_url = any(getattr(ev, "source_url", None) for ev in state.evidence)
        search_done = ClaimSearchPlanner.search_call_count(state) > 0
        has_uid = bool(pick_baidu_uid_from_evidence(list(state.evidence)))
        structured = state.structured_result or {}
        pending_disambiguation = bool(structured.get("place_disambiguation_pending"))
        if not has_uid and pending_disambiguation:
            for candidate in structured.get("place_disambiguation_candidates") or []:
                if isinstance(candidate, dict) and candidate.get("uid"):
                    has_uid = True
                    break
        filtered: list[str] = []
        for tool in queue:
            if tool in {"browser_mcp", "official_page_reader_mcp"} and not has_url and not search_done:
                continue
            if tool == "baidu_place_detail_mcp" and not has_uid:
                continue
            filtered.append(tool)
        return filtered

    def _non_search_priority_queue(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        allowed_names: set[str],
    ) -> list[str]:
        ordered: list[str] = []

        def _add(tool: str | None) -> None:
            if not tool or tool == "search_mcp" or tool not in allowed_names:
                return
            if tool not in ordered:
                ordered.append(tool)

        for tool in self._baidu_disambiguation_queue(state):
            _add(tool)

        for need in self._merged_information_needs(state):
            for tool in NEED_TOOL_PROFILES.get(need, []):
                _add(tool)

        plan = state.s5_domain_plan
        if plan:
            role_rank = {
                S5ToolRole.PRIMARY: 0,
                S5ToolRole.CANDIDATE: 1,
                S5ToolRole.ENRICHMENT: 2,
                S5ToolRole.FALLBACK: 3,
            }
            bindings = sorted(
                plan.tool_bindings,
                key=lambda b: (role_rank.get(b.role, 9), b.tool_name),
            )
            official_bindings = [
                b for b in bindings if b.provider_group == ProviderGroup.OFFICIAL_WEB_PROVIDER
            ]
            ticket_bindings = [
                b
                for b in bindings
                if b.domain == InformationDomain.TICKET_BOOKING or is_ticket_provider_tool(b.tool_name)
            ]
            provider_first = [b for b in ticket_bindings if is_ticket_provider_tool(b.tool_name)]
            other_ticket = [b for b in ticket_bindings if b not in provider_first]
            for binding in official_bindings + provider_first + other_ticket:
                _add(binding.tool_name)

        for tool in self._evidence_tool_queue(state, prompt_context):
            _add(tool)

        return ordered

    def _plan_gap_filling(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        from app.schemas.evidence_gap_request import EvidenceGapRequest

        gap_raw = prompt_context.get("gap_request") or {}
        gap = gap_raw if isinstance(gap_raw, EvidenceGapRequest) else EvidenceGapRequest.model_validate(gap_raw)
        max_steps = int(prompt_context.get("gap_max_extra_steps", gap.max_extra_steps))
        called: set[str] = set(prompt_context.get("_gap_called_tools", []))

        tools = [
            resolve_tool_name(t)
            for t in gap.suggested_tools
            if resolve_tool_name(t) not in set(gap.forbidden_tools)
            and resolve_tool_name(t) not in set(gap.failed_tools)
            and resolve_tool_name(t) not in set(gap.already_tried_tools)
        ]
        tools = [t for t in tools if t not in called]

        if step < len(tools) and step < max_steps:
            tool = tools[step]
            called.add(tool)
            prompt_context["_gap_called_tools"] = list(called)
            return self._make_call_tool_action(
                tool,
                state,
                prompt_context,
                reason_summary=f"S5 gap-fill tool for {gap.claim_type}: {tool}",
            )

        templates = list(gap.query_templates or [])
        search_idx = step - min(len(tools), max_steps)
        if search_idx >= 0 and search_idx < len(templates) and step < max_steps + len(templates):
            query = templates[search_idx]
            task_id = f"gap-{gap.gap_id[:8]}-{search_idx}"
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="keyword_search_agent",
                arguments={
                    "search_query": query,
                    "information_need": gap.claim_type,
                    "task_id": task_id,
                    "anchor_keywords": [state.semantic_frame.entities.places[0]]
                    if state.semantic_frame and state.semantic_frame.entities.places
                    else [],
                },
                reason_summary=f"S5 gap-fill search: {query[:48]}",
                confidence=0.8,
            )

        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments={"limitations": [f"S5 gap-fill completed for {gap.claim_type}"]},
            reason_summary="S5 gap-filling complete",
            confidence=0.85,
        )

    def _plan_evidence_aggregation(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        step: int,
    ) -> AgentAction:
        structured = dict(state.structured_result or {})
        plan = structured.get("curation_plan")
        curated = structured.get("curated_claims")
        conflict_done = structured.get("conflict_analyzed")

        if not plan:
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="evidence_curation_planner_agent",
                arguments={},
                reason_summary="S7: plan evidence curation from user needs",
                confidence=0.85,
            )
        if curated is None:
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="claim_relevance_filter_agent",
                arguments={},
                reason_summary="S7: filter claims by relevance to needs",
                confidence=0.85,
            )
        if plan.get("run_conflict_analysis") and not conflict_done:
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="evidence_conflict_analyzer_agent",
                arguments={},
                reason_summary="S7: analyze evidence conflicts",
                confidence=0.8,
            )

        from app.orchestrator.evidence_brief_builder import build_evidence_brief

        target = prompt_context.get("target_label") or "目的地"
        brief = build_evidence_brief(state, target)
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments={"result": brief.model_dump()},
            expected_output_schema="EvidenceBrief",
            reason_summary="S7: evidence curation complete",
            confidence=0.85,
        )

    @staticmethod
    def _search_call_count(state: TravelAgentState) -> int:
        return ClaimSearchPlanner.search_call_count(state)

    @staticmethod
    def _optional_prior_arguments(
        state: TravelAgentState,
        prompt_context: dict,
        allowed_names: set[str],
        called: set[str],
    ) -> dict | None:
        if "knowledge_prior" not in allowed_names or "knowledge_prior" in called:
            return None
        contract = state.response_contract
        if not contract:
            return None
        optional_prior = [
            c for c in contract.claim_requirements
            if c.claim_type == "general_seasonal_context" and c.model_prior_allowed
        ]
        if not optional_prior:
            return None
        search_done = sum(
            1 for t in state.tool_traces if resolve_tool_name(t.tool_name) == "search_mcp"
        )
        if search_done < 1:
            return None
        return {
            "information_need": "general_seasonal_context",
            "need_type": "general_seasonal_context",
        }

    @staticmethod
    def _search_tasks_from_state(state: TravelAgentState) -> list[dict]:
        structured = state.structured_result or {}
        tasks = structured.get("search_tasks") or []
        return tasks if isinstance(tasks, list) else []

    @staticmethod
    def _completed_search_task_ids(state: TravelAgentState) -> list[str]:
        structured = state.structured_result or {}
        completed = structured.get("completed_search_task_ids") or []
        return completed if isinstance(completed, list) else []

    def _next_pending_search_task(self, state: TravelAgentState) -> dict | None:
        if ClaimSearchPlanner.keyword_search_call_count(state) >= ClaimSearchPlanner.max_search_attempts(state):
            return None
        completed = set(self._completed_search_task_ids(state))
        for task in self._search_tasks_from_state(state):
            if not isinstance(task, dict):
                continue
            task_id = task.get("task_id")
            if task_id and task_id in completed:
                continue
            return task
        return None

    @staticmethod
    def _whitelist_names(prompt_context: dict) -> list[str]:
        whitelist = prompt_context.get("tool_whitelist")
        if whitelist is not None and hasattr(whitelist, "allowed_tool_names"):
            return whitelist.allowed_tool_names()
        allowed = prompt_context.get("allowed_tools") or []
        if allowed and isinstance(allowed[0], dict):
            return [t.get("name") for t in allowed if t.get("name")]
        return allowed

    @staticmethod
    def _needs_coordinate_resolution(state: TravelAgentState) -> bool:
        from tools.mcp.adapters.baidu_response_parser import resolve_coordinates_from_evidence

        if resolve_coordinates_from_evidence(list(state.evidence)):
            return False
        frame = state.semantic_frame
        if frame is None or frame.entities is None:
            return False
        country = (frame.entities.country or "").strip().lower()
        if country not in ("china", "中国"):
            return False
        return bool(frame.entities.places or frame.entities.city or frame.entities.region)

    @staticmethod
    def _baidu_disambiguation_queue(state: TravelAgentState) -> list[str]:
        """Baidu search → detail → geocode when China place lacks city/coordinates."""
        frame = state.semantic_frame
        if frame is None or frame.entities is None:
            return []
        country = (frame.entities.country or "").strip().lower()
        if country not in ("china", "中国"):
            return []
        needs = ActionModelController._merged_information_needs(state)
        if "ticket_price" in needs and (frame.entities.city or "").strip():
            return []
        if (frame.entities.city or "").strip() and not ActionModelController._needs_coordinate_resolution(
            state
        ):
            return []
        queue = ["baidu_place_search_mcp", "baidu_place_detail_mcp"]
        if ActionModelController._needs_coordinate_resolution(state):
            queue.append("baidu_geocode_mcp")
        return queue

    @staticmethod
    def _baidu_queue_prefix(frame) -> list[str]:
        """Backward-compatible alias; prefer _baidu_disambiguation_queue(state)."""
        if frame is None or frame.entities is None:
            return []
        country = (frame.entities.country or "").strip().lower()
        if country not in ("china", "中国"):
            return []
        if (frame.entities.city or "").strip():
            return []
        return ["baidu_place_search_mcp", "baidu_place_detail_mcp", "baidu_geocode_mcp"]

    @staticmethod
    def _china_baidu_tools(frame) -> list[str]:
        if frame is None or frame.entities is None:
            return []
        country = (frame.entities.country or "").strip().lower()
        if country not in ("china", "中国"):
            return []
        return ["baidu_place_search_mcp", "baidu_place_detail_mcp"]

    def _evidence_tool_queue(self, state: TravelAgentState, prompt_context: dict) -> list[str]:
        contract = state.response_contract
        if contract:
            queue = list(contract.tool_strategy.initial_tools)
            for claim in contract.claim_requirements:
                if claim.priority in ("required", "important"):
                    for tool in claim.preferred_tools:
                        if tool not in queue:
                            queue.append(tool)
            for tool in contract.entity_policy.preferred_tools:
                if tool not in queue:
                    queue.append(tool)
            for tool in contract.tool_strategy.fallback_tools:
                if tool not in queue:
                    queue.append(tool)
            deduped: list[str] = []
            for tool in queue:
                if tool not in deduped:
                    deduped.append(tool)
            return deduped

        frame = state.semantic_frame
        decision = state.answer_mode_decision
        needs = list(frame.information_needs) if frame else []
        if state.information_needs:
            needs.extend(n.need_type.value for n in state.information_needs)

        if frame and frame.decision_type == DecisionType.BEST_TIME_TO_VISIT:
            queue = [
                "search_mcp",
                "openmeteo_mcp",
                "climate_mcp",
                "wikidata_mcp",
                "wikipedia_mcp",
                "weather",
                "seasonality",
                "knowledge_prior",
            ]
            queue = self._baidu_disambiguation_queue(state) + queue
        elif frame and frame.decision_type == DecisionType.GENERAL_ADVICE:
            queue = ["search_mcp", "wikipedia_mcp", "wikidata_mcp", "places", "knowledge_prior", "fallback"]
        elif frame and frame.decision_type == DecisionType.WHETHER_TO_GO:
            queue = ["weather", "official", "places", "reviews", "weather_mcp"]
        elif any(n in needs for n in ("crowd_level", "queue_time", "current_crowd")):
            queue = ["search_mcp", "reviews", "places", "fallback"]
        elif any(n in needs for n in ("opening_hours", "ticket_price", "reservation_policy")):
            queue = [
                "search_mcp",
                "official_source_discovery_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
                "official",
                "fallback",
            ]
            queue = self._china_baidu_tools(frame) + queue
        elif any(n in needs for n in ("forecast", "weather", "weather_today", "today_weather")):
            queue = self._baidu_disambiguation_queue(state) + [
                "baidu_weather_mcp",
                "openmeteo_mcp",
                "weather_mcp",
                "weather",
                "fallback",
            ]
        elif frame and frame.decision_type == DecisionType.FACT_LOOKUP and frame.requires_exact_fact:
            queue = [
                "search_mcp",
                "official_source_discovery_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
                "official",
                "fallback",
            ]
        else:
            candidate = prompt_context.get("candidate_tool_plan") or {}
            queue = list(candidate.get("selected_tools") or ["places", "reviews", "weather"])

        if decision and not decision.allow_knowledge_prior:
            queue = [t for t in queue if t != "knowledge_prior"]
        elif decision and decision.allow_knowledge_prior and "knowledge_prior" not in queue:
            queue.append("knowledge_prior")

        deduped: list[str] = []
        for tool in queue:
            if tool not in deduped:
                deduped.append(tool)
        return deduped

    @staticmethod
    def _tool_arguments_for(tool: str, state: TravelAgentState, prompt_context: dict) -> dict:
        args: dict = {}
        frame = state.semantic_frame
        if frame:
            if frame.entities.places:
                args["place_name"] = frame.entities.places[0]
            if frame.entities.city:
                args["city"] = frame.entities.city
            if frame.entities.country:
                args["country"] = frame.entities.country
        if tool in {"official_page_reader_mcp", "browser_mcp"}:
            args["prior_evidence"] = list(state.evidence)
            need = ClaimSearchPlanner.primary_information_need(state)
            if need:
                args["information_need"] = need
            place = args.get("place_name") or ""
            if place and not args.get("url"):
                if need == "ticket_price":
                    args["query"] = f"{place} 官网 门票"
                elif need == "opening_hours":
                    args["query"] = f"{place} 官网 开放时间"
                else:
                    args["query"] = f"{place} 官网"
        if tool == "official_source_discovery_mcp":
            args["prior_evidence"] = list(state.evidence)
            need = ClaimSearchPlanner.primary_information_need(state)
            if need:
                args["claim_type"] = need
                args["information_need"] = need
            args["search_results"] = ClaimSearchPlanner.search_hits_from_evidence(state)
            args["probe_top_n"] = 1
            from tools.official_source.whitelist_resolver import resolve_official_whitelist_url

            place = args.get("place_name") or ""
            wl = resolve_official_whitelist_url(place)
            if wl:
                args.setdefault("urls", []).append(wl)
        if tool == "knowledge_prior":
            contract = state.response_contract
            if contract and any(
                c.claim_type == "general_seasonal_context" and c.model_prior_allowed
                for c in contract.claim_requirements
            ):
                args["information_need"] = "general_seasonal_context"
                args["need_type"] = "general_seasonal_context"
            else:
                frame = state.semantic_frame
                if frame and frame.information_needs:
                    args["information_need"] = frame.information_needs[0]
        if tool in {"search_mcp", "places_mcp", "baidu_place_search_mcp"}:
            if not args.get("query"):
                args["query"] = state.raw_user_query
            if not args.get("information_need"):
                args["information_need"] = ClaimSearchPlanner.primary_information_need(state)
        if is_ticket_provider_tool(tool):
            need = ClaimSearchPlanner.primary_information_need(state)
            if need:
                args.setdefault("information_need", need)
                args.setdefault("claim_type", need)
            if not args.get("query"):
                args["query"] = state.raw_user_query
        return args
