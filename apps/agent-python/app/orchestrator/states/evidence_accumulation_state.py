"""S6: explicit evidence and tool trace accumulation."""

from app.orchestrator.comparison_helpers import (
    active_place_name,
    filter_polluted_evidence,
    is_comparison_mode,
    stamp_evidence_place,
)
from app.orchestrator.trace import TraceRecorder
from app.schemas.evidence import Evidence
from app.schemas.user_query import TravelAgentState


class EvidenceAccumulationState:
    """S6: sync tool traces and mark evidence accumulated (no judgement)."""

    def __init__(self, tools=None) -> None:
        self.tools = tools

    def run(self, state: TravelAgentState, *, append: bool = False) -> TravelAgentState:
        if self.tools is not None:
            state.tool_traces = list(self.tools.traces)

        evidence = [ev for ev in state.evidence if isinstance(ev, Evidence)]
        if is_comparison_mode(state):
            place = active_place_name(state)
            if place:
                evidence = stamp_evidence_place(evidence, place)
                before = len(evidence)
                evidence = filter_polluted_evidence(evidence, place)
                dropped = before - len(evidence)
                if dropped:
                    TraceRecorder.add(state, f"✓ S6 过滤歧义证据：{place} -{dropped}")
        if not append:
            state.evidence = evidence
        else:
            seen = {ev.evidence_id for ev in evidence}
            merged = list(state.evidence)
            for ev in evidence:
                if ev.evidence_id not in seen:
                    merged.append(ev)
                    seen.add(ev.evidence_id)
            state.evidence = merged

        state.evidence_accumulated = True
        TraceRecorder.add(
            state,
            f"✓ S6 EvidenceAccumulation：{len(state.evidence)} evidence, {len(state.tool_traces)} tool traces",
        )
        return state
