from app.agents.conversation_context_builder import ConversationContextBuilder
from app.agents.query_understanding_agent import QueryUnderstandingAgent
from app.agents.semantic_frame_builder import SemanticFrameBuilder
from app.config import get_settings
from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.clarification_gate import ClarificationGate
from app.orchestrator.trace import TraceRecorder
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.semantic_frame import AnswerMode
from app.schemas.user_query import TravelAgentState, UserContext
from app.tools.capability_registry import CapabilityRegistry


class QueryUnderstandingPromptState:
    """Fixed controlled state — always runs before tool routing."""

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

        semantic_frame = result.semantic_frame or SemanticFrameBuilder.build(state.raw_user_query, result)
        result.semantic_frame = semantic_frame
        state.semantic_frame = semantic_frame

        caps = set(CapabilityRegistry().all_tool_names())
        state.answer_mode_decision = AnswerModeRouter().route(semantic_frame, caps)
        TraceRecorder.add(
            state,
            f"✓ AnswerMode：{state.answer_mode_decision.answer_mode.value}（{state.answer_mode_decision.reason[:60]}）",
        )
        if state.answer_mode_decision.limitations_to_add:
            state.limitations.extend(state.answer_mode_decision.limitations_to_add)

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
        if result.resolved_references:
            refs = ", ".join(f"{k}={v}" for k, v in result.resolved_references.items())
            TraceRecorder.add(state, f"✓ 已解析上下文指代：{refs}")
        TraceRecorder.add(state, f"✓ 已生成 TravelTask：{result.travel_task.task_type.value}")

        if ClarificationGate.apply(state):
            return state

        if state.answer_mode_decision.answer_mode == AnswerMode.CLARIFICATION_REQUIRED:
            state.next_state = "clarification_response"
            state.final_response = (
                state.rewritten_query_result.clarification_prompt
                if state.rewritten_query_result and state.rewritten_query_result.clarification_prompt
                else "请补充具体地点或出行时间，以便继续分析。"
            )
            return state

        state.next_state = "continue"
        return state
