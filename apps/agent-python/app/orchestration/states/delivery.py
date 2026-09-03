"""Build the public response from guarded, auditable artifacts."""

from app.contracts.response import AgentQueryResponse
from app.orchestration.state_contracts import AgentState, StateContext


class DeliveryHandler:
    async def build_response(self, context: StateContext) -> AgentQueryResponse:
        guarded = context.artifacts.get(AgentState.CITATION_GUARD.value, {})
        retrieval = context.artifacts.get(AgentState.HYBRID_RETRIEVE.value, {})
        evidence_index = guarded.get("evidence_index", {})
        citation_report = guarded.get("citation_report") or {}
        return AgentQueryResponse(
            answer=guarded.get("answer") or "当前证据不足，无法可靠回答。",
            session_id=context.session_id,
            query_id=context.query_id,
            evidence_summary=list(evidence_index.values()),
            limitations=(
                ["部分硬事实未通过引用校验。"]
                if citation_report.get("unsupported_hard_fact_count")
                else []
            ),
            confidence=float(citation_report.get("citation_precision", 0.0)),
            answer_claims=list(guarded.get("supported_claims", [])),
            citation_report=citation_report,
            retrieval_reports=list(retrieval.get("retrieval_reports", [])),
            metrics={
                "citation_precision": float(
                    citation_report.get("citation_precision", 0.0)
                )
            },
            orchestration_summary={
                "run_id": context.run_id,
                "terminal_state": AgentState.DELIVER.value,
            },
        )


__all__ = ["DeliveryHandler"]
