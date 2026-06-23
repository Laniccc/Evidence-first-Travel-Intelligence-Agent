from app.agents.answer_composer_agent import AnswerComposerAgent
from app.orchestrator.composition_preflight import (
    clear_premature_clarification_for_composition,
    should_compose_over_clarification,
)
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.state_policy import ANSWER_COMPOSITION_POLICY
from app.orchestrator.state_reducer import StateReducer
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState


class AnswerCompositionState:
    """S8: controlled loop for final answer composition (LLM only via runner)."""

    def __init__(self, llm_client=None) -> None:
        self.llm_client = llm_client
        self.runner = ClaudeStateRunner(llm_client)

    async def run(self, state: TravelAgentState, **compose_kwargs) -> TravelAgentState:
        prompt_context = dict(compose_kwargs)
        if clear_premature_clarification_for_composition(state):
            TraceRecorder.add(
                state,
                "✓ S8 清除 S5 过早地点澄清，改按 S7 claim_decisions 合成",
            )
        state = await self.runner.run(state, ANSWER_COMPOSITION_POLICY, prompt_context)
        if not (state.final_response or "").strip():
            TraceRecorder.add(state, "⚠ AnswerComposition 受控循环未产出答案，触发兜底合成")
            draft = await AnswerComposerAgent(self.llm_client).compose(state, prompt_context)
            state = StateReducer()._apply_composition_draft(state, draft)
        if state.final_response:
            TraceRecorder.add(state, "✓ 已完成 AnswerComposition")
        return state
