import json

from app.agents.information_need_planner import InformationNeedPlanner
from app.llm_client import LLMClient
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.claim_search_planner import ClaimSearchPlanner
from app.orchestrator.state_policy import StateNodePolicy
from app.policies.evidence_policy import EvidencePolicy
from app.schemas.semantic_frame import AnswerMode, DecisionType
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name


class ActionModelController:
    """Propose the next structured action — LLM when available, else deterministic plan."""

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
        if policy.state_name == "evidence_planning_and_tool_use":
            await self._maybe_expand_search_queries(state, prompt_context)
        if self.llm and self.llm._should_use_anthropic():
            try:
                action = await self._llm_action(state, policy, prompt_context, step)
                prompt_context["_last_action_source"] = "llm"
                return action
            except Exception:
                pass
        prompt_context["_last_action_source"] = "deterministic"
        return self._deterministic_action(state, policy, prompt_context, step)

    async def _maybe_expand_search_queries(
        self,
        state: TravelAgentState,
        prompt_context: dict,
    ) -> None:
        if prompt_context.get("claim_search_queries_expanded"):
            return
        seed = ClaimSearchPlanner.build_queries(state)
        extras = ClaimSearchPlanner.refine_queries_after_misses(state, set(seed))
        merged = ClaimSearchPlanner._dedupe([*seed, *extras])
        if self.llm._should_use_anthropic() and state.response_contract:
            from app.agents.search_query_refiner_agent import SearchQueryRefinerAgent

            try:
                llm_extra = await SearchQueryRefinerAgent(self.llm).propose(state, seed)
                merged = ClaimSearchPlanner._dedupe([*merged, *llm_extra])
            except Exception:
                pass
        prompt_context["claim_search_queries"] = merged
        prompt_context["claim_search_queries_expanded"] = True

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
                "Controlled A2A: prefer CALL_SUBAGENT search_task_planner_agent once, then "
                "multiple CALL_SUBAGENT keyword_search_agent tasks with anchor_keywords + search_query.\n"
                "anchor_keywords are strict; search_query may add associative terms but must include an anchor.\n"
                "Never call tools/subagents outside allowed lists. Never output final answer text."
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
                    "claim_search_queries": prompt_context.get("claim_search_queries", []),
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
            return self._plan_evidence_planning_and_tool_use(state, prompt_context, step)
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
        draft_data = (state.structured_result or {}).get("final_answer_draft")
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
        if draft_data is None and state.final_response:
            draft_data = {
                "answer_text": state.final_response,
                "conclusion": state.final_response[:200],
                "compose_mode": prompt_context.get("compose_mode", "advisory"),
            }
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

        queue = self._evidence_tool_queue(state, prompt_context)
        allowed_names = set(self._whitelist_names(prompt_context))
        if allowed_names:
            queue = [tool for tool in queue if tool in allowed_names]
        called = {resolve_tool_name(t.tool_name) for t in state.tool_traces}
        called |= {resolve_tool_name(t) for t in prompt_context.get("_called_policy_tools", [])}

        if not self._search_tasks_from_state(state):
            if not prompt_context.get("_search_task_planner_called"):
                prompt_context["_search_task_planner_called"] = True
                return AgentAction(
                    action_type=AgentActionType.CALL_SUBAGENT,
                    target="search_task_planner_agent",
                    arguments={},
                    reason_summary="A2A: plan keyword search tasks from ResponseContract",
                    confidence=0.85,
                )

        pending_task = self._next_pending_search_task(state)
        if pending_task:
            return AgentAction(
                action_type=AgentActionType.CALL_SUBAGENT,
                target="keyword_search_agent",
                arguments=pending_task,
                reason_summary=f"A2A keyword search: {pending_task.get('search_query', '')[:56]}",
                confidence=0.8,
            )

        next_search = self._next_claim_search_query(state, prompt_context, allowed_names)
        if next_search and not self._search_tasks_from_state(state):
            prompt_context.setdefault("_called_policy_tools", []).append("search_mcp")
            return AgentAction(
                action_type=AgentActionType.CALL_TOOL,
                target="search_mcp",
                arguments=next_search,
                reason_summary=f"Targeted search: {next_search.get('query', '')[:60]}",
                confidence=0.8,
            )

        prior_args = self._optional_prior_arguments(state, prompt_context, allowed_names, called)
        if prior_args:
            search_done = self._search_call_count(state)
            min_searches = min(3, ClaimSearchPlanner.max_search_attempts(state))
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

        next_tool = next((tool for tool in queue if resolve_tool_name(tool) not in called), None)
        if next_tool:
            prompt_context.setdefault("_called_policy_tools", []).append(next_tool)
            return AgentAction(
                action_type=AgentActionType.CALL_TOOL,
                target=next_tool,
                arguments=self._tool_arguments_for(next_tool, state, prompt_context),
                reason_summary=f"Retrieve evidence via {next_tool}",
                confidence=0.75,
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

    @staticmethod
    def _search_call_count(state: TravelAgentState) -> int:
        return sum(1 for t in state.tool_traces if resolve_tool_name(t.tool_name) == "search_mcp")

    def _next_claim_search_query(
        self,
        state: TravelAgentState,
        prompt_context: dict,
        allowed_names: set[str],
    ) -> dict | None:
        if "search_mcp" not in allowed_names:
            return None
        queries = prompt_context.get("claim_search_queries")
        if queries is None:
            queries = ClaimSearchPlanner.build_queries(state)
            prompt_context["claim_search_queries"] = queries
        idx = self._search_call_count(state)
        max_searches = ClaimSearchPlanner.max_search_attempts(state)

        if idx >= len(queries) and idx < max_searches:
            tried = {queries[i] for i in range(min(idx, len(queries)))}
            tried |= ClaimSearchPlanner._tried_from_traces(state)
            refined = ClaimSearchPlanner.refine_queries_after_misses(state, tried)
            if refined:
                prompt_context["claim_search_queries"] = ClaimSearchPlanner._dedupe(
                    [*queries, *refined]
                )
                queries = prompt_context["claim_search_queries"]

        if idx >= len(queries) or idx >= max_searches:
            return None
        need = ClaimSearchPlanner.primary_information_need(state)
        frame = state.semantic_frame
        return {
            "query": queries[idx],
            "information_need": need,
            "country": frame.entities.country if frame else None,
            "city": frame.entities.city if frame else None,
            "place_name": frame.entities.places[0] if frame and frame.entities.places else None,
        }

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
    def _baidu_queue_prefix(frame) -> list[str]:
        """Baidu first only for China when city is missing (place disambiguation)."""
        if frame is None or frame.entities is None:
            return []
        country = (frame.entities.country or "").strip().lower()
        if country not in ("china", "中国"):
            return []
        if (frame.entities.city or "").strip():
            return []
        return ["baidu_place_search_mcp", "baidu_place_detail_mcp"]

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
            queue = self._baidu_queue_prefix(frame) + queue
        elif frame and frame.decision_type == DecisionType.GENERAL_ADVICE:
            queue = ["search_mcp", "wikipedia_mcp", "wikidata_mcp", "places", "knowledge_prior", "fallback"]
        elif frame and frame.decision_type == DecisionType.WHETHER_TO_GO:
            queue = ["weather", "official", "places", "reviews", "weather_mcp"]
        elif any(n in needs for n in ("crowd_level", "queue_time", "current_crowd")):
            queue = ["search_mcp", "reviews", "places", "fallback"]
        elif any(n in needs for n in ("opening_hours", "ticket_price", "reservation_policy")):
            queue = [
                "search_mcp",
                "official_page_reader_mcp",
                "browser_mcp",
                "official",
                "fallback",
            ]
            queue = self._china_baidu_tools(frame) + queue
        elif any(n in needs for n in ("forecast", "weather", "weather_today", "today_weather")):
            queue = ["baidu_weather_mcp", "openmeteo_mcp", "weather_mcp", "weather", "fallback"]
        elif frame and frame.decision_type == DecisionType.FACT_LOOKUP and frame.requires_exact_fact:
            queue = [
                "search_mcp",
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
                queries = ClaimSearchPlanner.build_queries(state)
                args["query"] = queries[0] if queries else state.raw_user_query
            if not args.get("information_need"):
                args["information_need"] = ClaimSearchPlanner.primary_information_need(state)
        return args
