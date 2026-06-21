import json

from app.agents.information_need_planner import InformationNeedPlanner
from app.llm_client import LLMClient
from app.orchestrator.actions import AgentAction, AgentActionType
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
            system += (
                "\n\nS5 Evidence Planning rules:\n"
                + "\n".join(f"- {rule}" for rule in rules)
                + f"\nallowed_tools (ONLY these targets): {[t.get('name') for t in allowed]}\n"
                "Never call tools outside allowed_tools. Never output final answer text."
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
        decision = state.answer_mode_decision
        if decision and decision.answer_mode == AnswerMode.EVIDENCE_REQUIRED and not state.evidence:
            finish_args["evidence_gap_acknowledged"] = True
            finish_args["limitations"] = ["所需证据未能通过工具获取，将在后续回答中说明限制。"]
        return AgentAction(
            action_type=AgentActionType.FINISH_STATE,
            arguments=finish_args,
            reason_summary="Evidence sufficient or tool queue exhausted",
            confidence=0.8,
        )

    @staticmethod
    def _whitelist_names(prompt_context: dict) -> list[str]:
        whitelist = prompt_context.get("tool_whitelist")
        if whitelist is not None and hasattr(whitelist, "allowed_tool_names"):
            return whitelist.allowed_tool_names()
        allowed = prompt_context.get("allowed_tools") or []
        if allowed and isinstance(allowed[0], dict):
            return [t.get("name") for t in allowed if t.get("name")]
        return allowed

    def _evidence_tool_queue(self, state: TravelAgentState, prompt_context: dict) -> list[str]:
        frame = state.semantic_frame
        decision = state.answer_mode_decision
        needs = list(frame.information_needs) if frame else []
        if state.information_needs:
            needs.extend(n.need_type.value for n in state.information_needs)

        if frame and frame.decision_type == DecisionType.BEST_TIME_TO_VISIT:
            queue = ["weather", "seasonality", "search_mcp", "knowledge_prior"]
        elif frame and frame.decision_type == DecisionType.GENERAL_ADVICE:
            queue = ["search_mcp", "wikipedia_mcp", "wikidata_mcp", "places", "knowledge_prior", "fallback"]
        elif frame and frame.decision_type == DecisionType.WHETHER_TO_GO:
            queue = ["weather", "official", "places", "reviews", "weather_mcp"]
        elif any(n in needs for n in ("crowd_level", "queue_time", "current_crowd")):
            queue = ["reviews", "places", "fallback", "search_mcp"]
        elif any(n in needs for n in ("opening_hours", "ticket_price", "reservation_policy")):
            queue = ["official", "places", "official_page_reader_mcp", "browser_mcp", "search_mcp"]
        elif frame and frame.decision_type == DecisionType.FACT_LOOKUP and frame.requires_exact_fact:
            queue = ["official", "places", "official_page_reader_mcp", "browser_mcp", "search_mcp"]
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
            need = None
            frame = state.semantic_frame
            if frame and frame.information_needs:
                need = frame.information_needs[0]
            args["information_need"] = need
        if tool in {"search_mcp", "places_mcp"}:
            args["query"] = state.raw_user_query
        return args
