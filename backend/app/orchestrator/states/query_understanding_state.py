from app.agents.conversation_context_builder import ConversationContextBuilder
from app.agents.query_understanding_agent import QueryUnderstandingAgent
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.config import get_settings
from app.orchestrator.clarification_gate import ClarificationGate
from app.orchestrator.trace import TraceRecorder
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.user_query import TravelAgentState, UserContext


class QueryUnderstandingPromptState:
    """Fixed controlled state — always runs before AnswerMode routing."""

    def __init__(self, llm_client) -> None:
        self.context_builder = ConversationContextBuilder()
        self.agent = QueryUnderstandingAgent(llm_client)
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

        result = await self.agent.run(
            raw_query=state.raw_user_query,
            conversation_context=context,
            supported_regions=self.settings.supported_countries,
            user_ctx=user_ctx,
        )
        state.query_understanding = result
        state.travel_task = result.travel_task
        state.semantic_frame = SemanticFrameBuilder.attach(state.raw_user_query, result)

        state.rewritten_query_result = RewrittenQueryResult(
            rewritten_query=result.rewritten_query,
            resolved_references=result.resolved_references,
            missing_critical_info=result.missing_critical_info,
            needs_clarification=result.needs_clarification,
            clarification_prompt=result.clarification_question,
            assumptions=result.assumptions,
            confidence=result.confidence,
            key_concerns=result.key_concerns,
        )

        TraceRecorder.add(state, f"✓ 已完成用户问题转写：{result.rewritten_query[:80]}")
        if result.semantic_frame:
            sf = result.semantic_frame
            TraceRecorder.add(
                state,
                f"✓ SemanticFrame：scope={sf.query_scope.value} decision={sf.decision_type.value}",
            )
        if result.resolved_references:
            refs = ", ".join(f"{k}={v}" for k, v in result.resolved_references.items())
            TraceRecorder.add(state, f"✓ 已解析上下文指代：{refs}")
        TraceRecorder.add(state, f"✓ 已生成 TravelTask：{result.travel_task.task_type.value}")

        if ClarificationGate.apply(state):
            return state

        state.next_state = "continue"
        return state
