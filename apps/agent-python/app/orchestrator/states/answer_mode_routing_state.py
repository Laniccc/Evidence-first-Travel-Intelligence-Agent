from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry


class AnswerModeRoutingState:
    """Independent state: SemanticFrame → AnswerModeDecision (after QueryUnderstanding)."""

    def __init__(self, router: AnswerModeRouter | None = None) -> None:
        self.router = router or AnswerModeRouter()

    def run(self, state: TravelAgentState) -> TravelAgentState:
        if not state.semantic_frame:
            raise ValueError("semantic_frame required before AnswerModeRoutingState")

        caps = set(CapabilityRegistry().all_tool_names())
        state.answer_mode_decision = self.router.route(state.semantic_frame, caps)
        decision = state.answer_mode_decision
        TraceRecorder.add(
            state,
            f"✓ AnswerMode：{decision.answer_mode.value}（{decision.reason[:72]}）",
        )
        if decision.limitations_to_add:
            state.limitations.extend(decision.limitations_to_add)
        return state
