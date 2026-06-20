from app.agents.conversation_context_builder import ConversationContextBuilder
from app.config import get_settings
from app.orchestrator.clarification_gate import ClarificationGate
from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.state_policy import QUERY_UNDERSTANDING_POLICY
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState, UserContext


class QueryUnderstandingPromptState:
    """S2: ClaudeStateRunner wraps QueryUnderstandingAgent → FINISH_STATE(result=QU)."""

    def __init__(self, llm_client) -> None:
        self.context_builder = ConversationContextBuilder()
        self.runner = ClaudeStateRunner(llm_client)
        self.settings = get_settings()

    async def run(
        self,
        state: TravelAgentState,
        user_ctx: UserContext,
        user_context: dict | None = None,
    ) -> TravelAgentState:
        context = self.context_builder.build(state, user_context, user_ctx)
        state.conversation_context = context
        TraceRecorder.add(state, "✓ 已构建会话上下文")

        prompt_context = {
            "supported_regions": self.settings.supported_countries,
            "user_ctx": user_ctx,
        }
        state = await self.runner.run(state, QUERY_UNDERSTANDING_POLICY, prompt_context)

        result = state.query_understanding
        if result:
            TraceRecorder.add(state, f"✓ 已完成用户问题转写：{result.rewritten_query[:80]}")
            if result.resolved_references:
                refs = ", ".join(f"{k}={v}" for k, v in result.resolved_references.items())
                TraceRecorder.add(state, f"✓ 已解析上下文指代：{refs}")
            TraceRecorder.add(state, f"✓ 已生成 TravelTask：{result.travel_task.task_type.value}")

        if ClarificationGate.apply(state):
            return state

        state.next_state = "continue"
        return state
