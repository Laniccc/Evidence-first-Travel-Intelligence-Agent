from app.agents.conversation_context_builder import ConversationContextBuilder
from app.agents.llm_understanding_agent import LLMUnderstandingSubAgent
from app.agents.normalized_request_to_query_understanding import NormalizedRequestToQueryUnderstanding
from app.agents.normalized_request_to_semantic_frame import NormalizedRequestToSemanticFrame
from app.agents.normalized_request_to_travel_task import NormalizedRequestToTravelTask
from app.config import get_settings
from app.orchestrator.clarification_gate import ClarificationGate
from app.orchestrator.trace import TraceRecorder
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.user_query import TravelAgentState, UserContext


class LLMUnderstandingState:
    """S2: LLM-first understanding → NormalizedUserRequest → SemanticFrame / TravelTask."""

    def __init__(self, llm_client) -> None:
        self.context_builder = ConversationContextBuilder()
        self.agent = LLMUnderstandingSubAgent(llm_client)
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

        normalized = await self.agent.run(
            state.raw_user_query,
            context,
            user_ctx,
            supported_regions=self.settings.supported_countries,
        )
        state.normalized_request = normalized

        using_llm = self.agent.llm._should_use_anthropic()
        mode_label = "LLM" if using_llm else "规则回退（未配置 DEEPSEEK_API_KEY 或 LLM_MODE=mock）"

        frame = NormalizedRequestToSemanticFrame.convert(normalized)
        task = NormalizedRequestToTravelTask.convert(normalized, user_ctx)
        qu = NormalizedRequestToQueryUnderstanding.convert(normalized, frame, task)

        state.semantic_frame = frame
        state.travel_task = task
        state.query_understanding = qu
        state.rewritten_query_result = RewrittenQueryResult(
            rewritten_query=qu.rewritten_query,
            resolved_references=qu.resolved_references,
            missing_critical_info=qu.missing_critical_info,
            needs_clarification=qu.needs_clarification,
            clarification_prompt=qu.clarification_question,
            assumptions=qu.assumptions,
            confidence=qu.confidence,
            key_concerns=qu.key_concerns,
        )

        TraceRecorder.add(state, f"✓ 用户理解完成（{mode_label}）：{normalized.rewritten_query[:80]}")
        TraceRecorder.add(
            state,
            f"✓ NormalizedUserRequest：{normalized.query_scope}/{normalized.task_family}/"
            f"{normalized.decision_type} (confidence={normalized.confidence:.2f})",
        )
        if normalized.entities:
            names = ", ".join(e.normalized_name or e.text for e in normalized.entities[:3])
            TraceRecorder.add(state, f"✓ 识别实体：{names}")
        TraceRecorder.add(
            state,
            f"✓ SemanticFrame：{frame.query_scope.value}/{frame.decision_type.value}",
        )
        TraceRecorder.add(state, f"✓ 已生成 TravelTask：{task.task_type.value}")

        if ClarificationGate.apply(state):
            return state

        state.next_state = "continue"
        return state
