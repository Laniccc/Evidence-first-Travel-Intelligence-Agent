from app.orchestrator.claude_state_runner import ClaudeStateRunner
from app.orchestrator.evidence_brief_builder import apply_evidence_brief, build_evidence_brief
from app.orchestrator.evidence_evaluator import evaluate_evidence
from app.orchestrator.non_lookup_task_chains import (
    evaluate_non_lookup_task_evidence,
    is_non_lookup_task,
)
from app.orchestrator.state_policy import EVIDENCE_AGGREGATION_POLICY
from app.orchestrator.trace import TraceRecorder
from app.schemas.user_query import TravelAgentState


class EvidenceAggregationState:
    """S7: Evidence Evaluation / Cross-source Judgement (deterministic + optional LLM assist)."""

    def __init__(self, llm_client=None) -> None:
        self.llm_client = llm_client
        self.runner = ClaudeStateRunner(llm_client)

    async def run(self, state: TravelAgentState, **ctx) -> TravelAgentState:
        prompt_context = dict(ctx)
        target = prompt_context.get("target_label") or "目的地"

        if is_non_lookup_task(state):
            report = evaluate_non_lookup_task_evidence(state)
        else:
            report = evaluate_evidence(state, target_label=target)
        state.evidence_decision_report = report
        state.pending_evidence_gap_requests = list(report.evidence_gap_requests)
        TraceRecorder.add(
            state,
            f"✓ S7 EvidenceEvaluation：{len(report.claim_decisions)} claim decisions, "
            f"{len(report.evidence_gap_requests)} gap requests",
        )

        state = await self.runner.run(state, EVIDENCE_AGGREGATION_POLICY, prompt_context)

        brief = build_evidence_brief(state, target)
        apply_evidence_brief(state, brief)
        TraceRecorder.add(
            state,
            f"✓ S7 EvidenceBrief：{len(state.evidence_brief.curated_claims if state.evidence_brief else [])} curated claims",
        )
        return state
