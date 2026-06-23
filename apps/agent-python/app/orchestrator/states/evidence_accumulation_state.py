"""S6: explicit evidence and tool trace accumulation."""

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
