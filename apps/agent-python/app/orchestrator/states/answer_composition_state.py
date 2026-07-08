from app.agents.answer_composer_agent import AnswerComposerAgent
from app.orchestrator.composition_preflight import (
    clear_premature_clarification_for_composition,
    should_compose_over_clarification,
)
from app.orchestrator.nearby_guided_composition import prepare_nearby_guided_compose_context
from app.orchestrator.nearby_task_orchestration import should_use_nearby_guided_compose
from app.orchestrator.fact_lookup_guided_composition import prepare_fact_lookup_guided_compose_context
from app.orchestrator.fact_lookup_task_orchestration import should_use_fact_lookup_guided_compose
from app.orchestrator.non_lookup_task_chains import (
    prepare_non_lookup_task_compose_context,
    should_use_non_lookup_task_context,
)
from app.orchestrator.place_disambiguation_composition import (
    prepare_place_disambiguation_compose_context,
    should_present_place_disambiguation_at_s8,
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
        if should_use_nearby_guided_compose(state):
            prompt_context = prepare_nearby_guided_compose_context(state, prompt_context)
            TraceRecorder.add(
                state,
                "✓ S8 片区周边引导合成：先给可执行推荐，再轻量消歧",
            )
        elif should_use_fact_lookup_guided_compose(state):
            prompt_context = prepare_fact_lookup_guided_compose_context(state, prompt_context)
            TraceRecorder.add(
                state,
                "✓ S8 硬事实引导合成：先结论后来源，无法确认则明说",
            )
        elif should_present_place_disambiguation_at_s8(state):
            prompt_context = prepare_place_disambiguation_compose_context(state, prompt_context)
            TraceRecorder.add(
                state,
                "✓ S8 地点消歧呈现：列出候选地点及证据，引导用户选择",
            )
        elif should_use_non_lookup_task_context(state):
            prompt_context = prepare_non_lookup_task_compose_context(state, prompt_context)
            task_class = prompt_context.get("non_lookup_task_profile", {}).get("task_class", "non_lookup")
            TraceRecorder.add(state, f"✓ S8 non-lookup task context: {task_class}")
        elif clear_premature_clarification_for_composition(state):
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
