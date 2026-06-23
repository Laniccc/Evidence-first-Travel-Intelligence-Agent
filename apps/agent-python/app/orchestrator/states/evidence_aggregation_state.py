from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.evidence_brief_builder import apply_evidence_brief, build_evidence_brief
from app.orchestrator.state_policy import EVIDENCE_AGGREGATION_POLICY
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState


class EvidenceAggregationState:
    """S7: LLM-guided evidence curation loop."""

    def __init__(self, llm_client=None) -> None:
        self.llm_client = llm_client
        self.runner = ClaudeStateRunner(llm_client)

    async def run(self, state: TravelAgentState, **ctx) -> TravelAgentState:
        prompt_context = dict(ctx)
        state = await self.runner.run(state, EVIDENCE_AGGREGATION_POLICY, prompt_context)
        target = prompt_context.get("target_label") or "目的地"
        if state.evidence_brief is None:
            brief = build_evidence_brief(state, target)
            apply_evidence_brief(state, brief)
        TraceRecorder.add(
            state,
            f"✓ S7 EvidenceBrief：{len(state.evidence_brief.curated_claims if state.evidence_brief else [])} curated claims",
        )
        return state
