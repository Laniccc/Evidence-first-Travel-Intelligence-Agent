from app.agents.answer_composer_agent import AnswerComposerAgent
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.state_policy import ANSWER_COMPOSITION_POLICY
from app.orchestrator.state_reducer import StateReducer
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState


class AnswerCompositionState:
    """S8: controlled loop for final answer composition."""

    def __init__(self, llm_client=None) -> None:
        self.llm_client = llm_client
        self.runner = ClaudeStateRunner(llm_client)

    async def run(self, state: TravelAgentState, **compose_kwargs) -> TravelAgentState:
        prompt_context = dict(compose_kwargs)
        state = await self.runner.run(state, ANSWER_COMPOSITION_POLICY, prompt_context)
        if not (state.final_response or "").strip():
            compose_args = {k: v for k, v in prompt_context.items() if k != "user_ctx"}
            draft = await AnswerComposerAgent(self.llm_client).compose(state, compose_args)
            state = StateReducer()._apply_composition_draft(state, draft)
            TraceRecorder.add(state, "✓ AnswerComposition 兜底合成已执行")
        if state.final_response:
            TraceRecorder.add(state, "✓ 已完成 AnswerComposition")
        return state
