"""Optional one-shot maintenance; never expands the already evaluated answer."""
import asyncio

from app.contracts.mcp_evidence import McpEvidenceEnvelope
from app.governance.failure_reason import FailureClass
from app.orchestration.state_contracts import AgentState, RecoveryRecord, StateResult


class KnowledgePromotionHandler:
    def __init__(self, *, extractor, service, name_resolver, io_runner):
        self.extractor, self.service = extractor, service
        self.name_resolver, self.io_runner = name_resolver, io_runner

    async def run(self, context):
        evaluation = context.artifacts.get(AgentState.EVIDENCE_EVALUATE.value, {})
        resume = evaluation.get("promotion_resume_state", "safe_failure")
        allowed = {"compose", "safe_failure", "limited_answer"}
        if resume not in allowed or AgentState.KNOWLEDGE_PROMOTE.value in context.artifacts:
            return StateResult.succeeded(next_state=AgentState.SAFE_FAILURE,
                output={"failure_code": "promotion_illegal_resume"})
        output = {"resume_state": resume, "results": [], "llm_attempts": 0,
                  "run_id": context.run_id, "query_id": context.query_id, "trace_id": context.trace_id,
                  "failure_code": None}
        # Policy-disabled maintenance does not send provider content to another model.
        if not self.service.validator.policy.storage_enabled:
            output["failure_code"] = "storage_not_permitted"
        else:
            try:
                envelopes = [McpEvidenceEnvelope.model_validate(e) for e in context.artifacts.get(
                    AgentState.LIVE_GAP_FILL.value, {}).get("mcp_envelopes", [])]
                extracted = await self.extractor.extract(envelopes)
                output.update(llm_attempts=extracted.attempts, failure_code=extracted.failure_code,
                    prompt_hash=extracted.prompt_hash, schema_hash=extracted.schema_hash)
                context.versions["promotion_policy"] = self.service.validator.policy.version
                for candidate in extracted.candidates:
                    async with asyncio.timeout(5):
                        result = await self.io_runner("postfilter", self.service.promote,
                            candidate, envelopes, name=self.name_resolver(envelopes[0].attraction_id),
                            run_id=context.run_id, query_id=context.query_id, trace_id=context.trace_id or context.run_id)
                    output["results"].append(result)
            except TimeoutError:
                # A SQLite worker is not killable: report uncertainty, never retry the write.
                output["failure_code"] = "promotion_persistence_unknown"
            except Exception:
                output["failure_code"] = "promotion_failed"
        if output["failure_code"]:
            return StateResult(status="recovered", next_state=AgentState(resume), output=output,
                recovery=RecoveryRecord(strategy="preserve_transient_evidence",
                    recovered_from=FailureClass.POLICY_DENIED if output["failure_code"] == "storage_not_permitted" else FailureClass.DEPENDENCY_UNAVAILABLE,
                    attempt=1))
        return StateResult.succeeded(next_state=AgentState(resume), output=output)
