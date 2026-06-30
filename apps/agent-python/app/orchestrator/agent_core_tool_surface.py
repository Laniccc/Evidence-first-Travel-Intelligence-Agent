"""Agent Core phase tool surface.

The RootAgentSupervisor owns phase order. This surface only exposes concrete
phase tools; it no longer delegates control flow to the legacy state machine
dispatch methods.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.orchestrator.trace import TraceRecorder
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.response import TravelQueryResponse
from app.schemas.user_query import TravelAgentState, UserContext


@dataclass
class RunEnvelope:
    query: str
    user_context: dict | None
    session_id: str | None
    ctx: UserContext
    memory: ConversationMemory
    state: TravelAgentState


class PhaseToolSurface:
    def __init__(self, runtime) -> None:
        self.runtime = runtime

    async def build_input_contract(self, envelope: RunEnvelope) -> TravelAgentState | TravelQueryResponse:
        state = envelope.state
        state = await self.runtime._run_query_understanding(state, envelope.ctx, envelope.user_context)
        envelope.state = state
        if state.next_state == "clarification_response":
            confidence = state.query_understanding.confidence if state.query_understanding else 0.3
            return self.runtime._to_response(state, confidence)

        state = self.runtime._derive_intent_profile(state)
        state = self.runtime._run_answer_mode_routing(state)
        envelope.state = state
        return state

    def requires_clarification(self, envelope: RunEnvelope) -> bool:
        state = envelope.state
        contract = state.response_contract
        if contract and contract.clarification_policy.should_ask:
            return True
        decision = state.answer_mode_decision
        mode = decision.answer_mode if decision else None
        return bool(mode and getattr(mode, "value", mode) == "clarification_required")

    def clarification_response(self, envelope: RunEnvelope) -> TravelQueryResponse:
        state = envelope.state
        contract = state.response_contract
        if contract and contract.clarification_policy.should_ask:
            return self.runtime._clarification_from_contract(state)
        return self.runtime._clarification_from_answer_mode(state)

    async def apply_region_policy(self, envelope: RunEnvelope) -> TravelAgentState | TravelQueryResponse:
        state = envelope.state
        gate_query = (
            state.rewritten_query_result.rewritten_query
            if state.rewritten_query_result
            else envelope.query
        )
        blocked = self.runtime._apply_region_gate(
            state,
            envelope.query,
            gate_query,
            envelope.memory,
        )
        if blocked:
            return blocked

        state.user_goal = await self.runtime._resolve_user_goal(state, envelope.ctx, gate_query)
        self.runtime._complete_context(state, envelope.ctx)
        party = ", ".join(p.value for p in state.user_goal.party) if state.user_goal else ""
        TraceRecorder.add(state, f"Agent Core: user goal resolved ({party or 'general traveler'})")
        envelope.state = state
        return state

    async def run_evidence_acquisition_and_review(self, envelope: RunEnvelope) -> TravelAgentState:
        state = envelope.state
        target = self.runtime._resolve_target_label(state)
        state = await self.runtime._run_evidence_loop(
            state,
            place_name=target,
            place_context=self.runtime._place_context_for(state, target, 0),
            reset_evidence=True,
        )
        envelope.state = state
        return state

    async def compose_answer_draft(self, envelope: RunEnvelope) -> TravelAgentState:
        state = envelope.state
        target = self.runtime._resolve_target_label(state)
        state = await self.runtime._run_answer_composition(
            state,
            compose_mode=self.runtime._resolve_compose_mode(state),
            target_label=target,
            place_name=target,
        )
        envelope.state = state
        return state

    def run_citation_guard(self, envelope: RunEnvelope) -> float:
        state = envelope.state
        brief = state.evidence_brief
        base_confidence = brief.overall_confidence if brief else 0.45
        return self.runtime._citation_check(state, [], [], base_confidence)

    def deliver(self, envelope: RunEnvelope, confidence: float) -> TravelQueryResponse:
        return self.runtime._to_response(envelope.state, confidence)
