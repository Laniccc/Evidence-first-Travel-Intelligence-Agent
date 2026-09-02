from typing import Any

from app.composition.answer_claim import AnswerClaim
from app.composition.final_answer_draft import FinalAnswerDraft
from app.evidence.evidence_decision_report import ClaimDecision
from app.evidence.retrieval.report import RetrievalReport
from app.governance.failure_reason import FailureClass
from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateResult,
)

from app.composition.answer_composer import AnswerComposerAgent
from app.composition.composition_preflight import (
    clear_premature_clarification_for_composition,
    should_compose_over_clarification,
)
from app.composition.nearby_guided_composition import prepare_nearby_guided_compose_context
from app.composition.fact_lookup_guided_composition import prepare_fact_lookup_guided_compose_context
from app.composition.place_disambiguation_composition import (
    prepare_place_disambiguation_compose_context,
    should_present_place_disambiguation_at_s8,
)
from app.observability.trace import TraceRecorder
from app.orchestration.fact_lookup_task_orchestration import should_use_fact_lookup_guided_compose
from app.orchestration.non_lookup_task_chains import (
    prepare_non_lookup_task_compose_context,
    should_use_non_lookup_task_context,
)
from app.planning.nearby_task_orchestration import should_use_nearby_guided_compose
from app.orchestration.state_policy import ANSWER_COMPOSITION_POLICY
from app.orchestration.state_reducer import StateReducer
from app.orchestration.claude_state_runner import ClaudeStateRunner

TravelAgentState = Any


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


class GroundedCompositionHandler:
    """Compose typed claims; repair once, then use a deterministic evidence template."""

    def __init__(self, *, composer=None) -> None:
        self._composer = composer

    async def run(self, context: StateContext) -> StateResult:
        evaluation = context.artifacts.get(AgentState.EVIDENCE_EVALUATE.value, {})
        decisions = [
            ClaimDecision.model_validate(item)
            for item in evaluation.get("claim_decisions", [])
        ]
        allowed_fact_types = set(evaluation.get("common_fact_types") or [])
        accepted = [
            item
            for item in decisions
            if item.adoption in {"adopt", "adopt_with_limitation"}
            and item.adopted_value
            and (not allowed_fact_types or item.claim_type in allowed_fact_types)
        ]
        fallback_claims = [
            AnswerClaim(
                claim_id=item.claim_id or f"claim-{index}",
                text=item.adopted_value,
                claim_type=item.claim_type,
                hard_fact=True,
                evidence_ids=item.adopted_evidence_ids,
                attraction_id=item.attraction_id,
                subtask_id=item.subtask_id,
                conflict_disclosed=bool(item.conflict_evidence_ids),
            )
            for index, item in enumerate(accepted, start=1)
        ]
        evidence_index = _build_evidence_index(context)
        if not fallback_claims:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "no_accepted_claims", "answer_claims": []},
            )

        bundle = {
            "query": context.raw_query,
            "accepted_claims": [item.model_dump(mode="json") for item in fallback_claims],
            "allowed_evidence_ids": sorted(evidence_index),
        }
        recovery = None
        draft = None
        if self._composer is not None:
            for attempt, repair in enumerate((False, True), start=1):
                try:
                    candidate = await self._composer.compose_claims(bundle, repair=repair)
                    validated = FinalAnswerDraft.model_validate(candidate)
                    if not validated.answer_claims or not validated.render_text().strip():
                        raise ValueError("composer returned no claims or answer text")
                    draft = validated
                    if repair:
                        recovery = RecoveryRecord(
                            strategy="composition_repair_once",
                            recovered_from=FailureClass.PARSE_ERROR,
                            attempt=attempt,
                        )
                    break
                except Exception:
                    continue

        mode = "model"
        if draft is None:
            mode = "deterministic_fallback"
            answer = _render_claims(fallback_claims)
            draft = FinalAnswerDraft(
                headline="基于当前有效证据",
                conclusion=answer,
                answer_text=answer,
                answer_claims=fallback_claims,
                cited_evidence_ids=sorted(
                    {
                        evidence_id
                        for claim in fallback_claims
                        for evidence_id in claim.evidence_ids
                    }
                ),
                limitations=(
                    ["存在来源冲突，已保留并披露。"]
                    if any(claim.conflict_disclosed for claim in fallback_claims)
                    else []
                ),
                compose_mode="claim_grounded",
            )
            if self._composer is not None:
                recovery = RecoveryRecord(
                    strategy="deterministic_composition_fallback",
                    recovered_from=FailureClass.PARSE_ERROR,
                    attempt=2,
                )

        output = {
            "final_answer_draft": draft.model_dump(mode="json"),
            "answer_claims": [item.model_dump(mode="json") for item in draft.answer_claims],
            "evidence_index": evidence_index,
            "composition_mode": mode,
        }
        if recovery:
            return StateResult(
                status="recovered",
                next_state=AgentState.CITATION_GUARD,
                output=output,
                recovery=recovery,
            )
        return StateResult.succeeded(next_state=AgentState.CITATION_GUARD, output=output)


def _build_evidence_index(context: StateContext) -> dict[str, dict]:
    index = {}
    reports = context.artifacts.get(AgentState.HYBRID_RETRIEVE.value, {}).get(
        "retrieval_reports", []
    )
    for raw_report in reports:
        report = RetrievalReport.model_validate(raw_report)
        for hit in report.final_hits:
            index[hit.chunk_id] = {
                "evidence_id": hit.chunk_id,
                "source_url": hit.source_url,
                "document_version_id": hit.document_version_id,
                "version_status": "active",
                "content_hash": hit.content_hash,
                "active_content_hash": hit.content_hash,
                "content": hit.content,
                "attraction_id": hit.attraction_id,
                "fact_type": hit.fact_type,
                "source_id": hit.source_id,
                "corpus_version": hit.corpus_version,
            }
    for item in context.artifacts.get(AgentState.LIVE_GAP_FILL.value, {}).get(
        "transient_evidence", []
    ):
        evidence_id = item["evidence_id"]
        index[evidence_id] = {
            **item,
            "version_status": "transient",
            "content_hash": f"transient:{evidence_id}",
            "active_content_hash": f"transient:{evidence_id}",
        }
    return index


def _render_claims(claims: list[AnswerClaim]) -> str:
    return "\n".join(
        f"- {claim.text}（证据：{', '.join(claim.evidence_ids)}）"
        for claim in claims
    )
