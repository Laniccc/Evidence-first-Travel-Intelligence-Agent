"""Claim-grounded answer composition for the bounded RAG state chain."""
from hashlib import sha256
import asyncio

from app.composition.answer_claim import AnswerClaim
from app.composition.final_answer_draft import FinalAnswerDraft
from app.evidence.evidence_decision_report import ClaimDecision
from app.evidence.retrieval.report import RetrievalReport
from app.governance.failure_reason import FailureClass
from app.integrations.llm.client import ModelTransportError
from app.orchestration.state_contracts import (
    AgentState,
    RecoveryRecord,
    StateContext,
    StateResult,
)


class GroundedCompositionHandler:
    """One bounded proposal; any failure retains the complete evidence template."""

    def __init__(self, *, composer=None, timeout_seconds=2.0) -> None:
        self._composer = composer
        self._timeout_seconds = timeout_seconds

    async def run(self, context: StateContext) -> StateResult:
        context.versions["composition_policy"] = "complete-claim-order-v1"
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
        failure_code = None
        failure_class = FailureClass.PARSE_ERROR
        if self._composer is not None:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    candidate = await self._composer.compose_claims(bundle, repair=False)
                validated = FinalAnswerDraft.model_validate(candidate)
                expected = {c.claim_id: c.model_dump(mode="json") for c in fallback_claims}
                actual = {c.claim_id: c.model_dump(mode="json") for c in validated.answer_claims}
                if len(validated.answer_claims) != len(fallback_claims) or actual != expected:
                    raise ValueError("composer_modified_claims")
                # Only the verified ordering survives. Ignore all free-form draft text.
                draft = FinalAnswerDraft(answer_claims=validated.answer_claims,
                    answer_text=_render_claims(validated.answer_claims),
                    cited_evidence_ids=sorted({e for c in fallback_claims for e in c.evidence_ids}),
                    compose_mode="claim_grounded")
            except TimeoutError:
                failure_code, failure_class = "composer_timeout", FailureClass.TIMEOUT
            except ModelTransportError as exc:
                failure_code = exc.code.value
                failure_class = (FailureClass.RATE_LIMIT if failure_code == "llm_rate_limited"
                    else FailureClass.TIMEOUT if failure_code == "llm_timeout"
                    else FailureClass.DEPENDENCY_UNAVAILABLE)
            except (ValueError, TypeError, KeyError):
                failure_code = "composer_invalid_output"
            except Exception:
                failure_code, failure_class = "composer_unavailable", FailureClass.DEPENDENCY_UNAVAILABLE

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
                    recovered_from=failure_class,
                    attempt=1,
                )

        output = {
            "final_answer_draft": draft.model_dump(mode="json"),
            "answer_claims": [item.model_dump(mode="json") for item in draft.answer_claims],
            "evidence_index": evidence_index,
            "composition_mode": mode,
            "failure_code": failure_code,
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
                "subtask_id": report.subtask_id,
                "valid_from": hit.valid_from,
                "valid_to": hit.valid_to,
                "text_hash": sha256(hit.content.encode()).hexdigest(),
            }
    for item in context.artifacts.get(AgentState.LIVE_GAP_FILL.value, {}).get(
        "transient_evidence", []
    ):
        evidence_id = item["evidence_id"]
        index[evidence_id] = {
            **item,
            "version_status": "transient",
            "content_hash": item.get("content_hash"),
            "active_content_hash": item.get("content_hash"),
        }
    return index


def _render_claims(claims: list[AnswerClaim]) -> str:
    return "\n".join(
        f"- {claim.text}（证据：{', '.join(claim.evidence_ids)}）"
        for claim in claims
    )


__all__ = ["GroundedCompositionHandler"]
