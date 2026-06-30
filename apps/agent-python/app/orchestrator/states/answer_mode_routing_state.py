from app.orchestrator.answer_mode_router import AnswerModeRouter
from app.orchestrator.response_contract_compiler import ResponseContractCompiler
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState
from app.tools.capability_registry import CapabilityRegistry


class AnswerModeRoutingState:
    """Independent state: SemanticFrame → AnswerModeDecision (after QueryUnderstanding)."""

    def __init__(self, router: AnswerModeRouter | None = None) -> None:
        self.router = router or AnswerModeRouter()
        self.contract_compiler = ResponseContractCompiler()

    def run(self, state: TravelAgentState) -> TravelAgentState:
        if not state.semantic_frame:
            raise ValueError("semantic_frame required before AnswerModeRoutingState")

        caps = set(CapabilityRegistry().all_tool_names())
        state.answer_mode_decision = self.router.route(state.semantic_frame, caps)
        decision = state.answer_mode_decision

        contract = self.contract_compiler.compile(
            state.semantic_frame,
            state.normalized_request,
            conversation_context=state.conversation_context.model_dump() if state.conversation_context else None,
            available_tools=caps,
            intent_profile=state.intent_profile,
        )
        contract.derived_debug_answer_mode = decision.answer_mode.value
        state.response_contract = contract
        from app.orchestrator.claim_compiler import compile_lookup_claims

        lookup_claims = compile_lookup_claims(
            state.semantic_frame,
            state.raw_user_query,
            intent_profile=state.intent_profile,
        )
        if lookup_claims:
            structured = dict(state.structured_result or {})
            structured["lookup_claims"] = [lc.model_dump() for lc in lookup_claims]
            state.structured_result = structured

        claim_types = ", ".join(c.claim_type for c in contract.claim_requirements) or "none"
        TraceRecorder.add(state, f"✓ 已生成 ResponseContract：{claim_types}")
        required_summary = ", ".join(
            f"{c.claim_type}({c.priority})" for c in contract.claim_requirements if c.priority == "required"
        )
        if required_summary:
            TraceRecorder.add(state, f"✓ Claim 证据要求：{required_summary}")

        TraceRecorder.add(
            state,
            f"✓ AnswerMode（debug）：{decision.answer_mode.value}（{decision.reason[:72]}）",
        )
        if decision.limitations_to_add:
            state.limitations.extend(decision.limitations_to_add)
        state.limitations.extend(contract.limitations_to_add)
        return state
