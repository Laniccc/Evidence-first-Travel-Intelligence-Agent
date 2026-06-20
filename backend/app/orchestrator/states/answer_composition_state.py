from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.state_policy import ANSWER_COMPOSITION_POLICY
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState


class AnswerCompositionState:
    """S8: controlled loop for final answer composition."""

    def __init__(self, llm_client=None) -> None:
        self.runner = ClaudeStateRunner(llm_client)

    async def run(self, state: TravelAgentState, **compose_kwargs) -> TravelAgentState:
        prompt_context = dict(compose_kwargs)
        state = await self.runner.run(state, ANSWER_COMPOSITION_POLICY, prompt_context)
        if state.final_response:
            TraceRecorder.add(state, "✓ 已完成 AnswerComposition")
        return state
