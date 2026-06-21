import json

from app.llm_client import LLMClient
from app.orchestrator.actions import AgentAction, AgentActionType
from app.orchestrator.state_policy import StateNodePolicy
from app.schemas.user_query import TravelAgentState


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
            return self._deterministic_action(state, policy, prompt_context, step)
        if self.llm and self.llm._should_use_anthropic():
            try:
                return await self._llm_action(state, policy, prompt_context, step)
            except Exception:
                pass
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
            f"allowed_tools={policy.allowed_tools}\n"
            f"max_steps={policy.max_steps}, current_step={step + 1}\n"
            "Schema: {action_type, target, arguments, reason_summary, confidence}"
        )
        user = json.dumps(
            {
                "raw_query": state.raw_user_query,
                "step": step,
                "has_query_understanding": state.query_understanding is not None,
                "has_semantic_frame": state.semantic_frame is not None,
                "has_final_response": bool(state.final_response),
                "prompt_context_keys": list(prompt_context.keys()),
                "compose_mode": prompt_context.get("compose_mode"),
            },
            ensure_ascii=False,
        )
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
