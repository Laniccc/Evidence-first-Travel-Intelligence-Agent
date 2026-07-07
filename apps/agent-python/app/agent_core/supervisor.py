"""Root supervisor for the Research Agent pipeline — drives 6 phases."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent_core.contracts.gate_checks import check_delivery_gate, check_input_gate
from app.agent_core.gate import PipelineGate
from app.agent_core.state.lifecycle import FULL_PHASE_ORDER
from app.agent_core.store import AgentCoreStore
from app.agent_core.supervisor_policy import AgentCoreSupervisorPolicy
from app.agent_core.tool_surface import AgentCoreToolSurface

logger = logging.getLogger(__name__)

SAFETY_LIMITS = {
    "max_run_duration_seconds": 300,
}


class AgentCoreSupervisor:
    """Deterministic supervisor driving the 6-phase research pipeline."""

    def __init__(
        self,
        store: AgentCoreStore,
        *,
        tools_registry: Any | None = None,
        llm_client: Any = None,
        rag_store: Any = None,
        embedding_fn: Any = None,
    ) -> None:
        self.store = store
        self.surface = AgentCoreToolSurface(
            store,
            tools_registry=tools_registry,
            llm_client=llm_client,
            rag_store=rag_store,
            embedding_fn=embedding_fn,
        )
        self.gate = PipelineGate()
        self.policy = AgentCoreSupervisorPolicy()
        self._started_at = time.time()

    async def run(self, *, query: str, user_context: dict | None = None) -> dict[str, Any]:
        """Execute the full research pipeline."""
        # Gate 1: Input (only hard gate)
        input_result = check_input_gate(query)
        if input_result.action == "return_to_user":
            return {"status": "clarification_needed", "message": input_result.feedback}

        # Ingress: create run
        run_id = self.surface.ingress(query=query, user_context=user_context)

        all_evidence: list[Any] = []
        final_report: dict[str, Any] = {}
        completed_phases: list[str] = []
        plan_queries: list[dict[str, str]] = []
        rag_evidence: list[dict] = []

        for phase_name in FULL_PHASE_ORDER:
            if time.time() - self._started_at > SAFETY_LIMITS["max_run_duration_seconds"]:
                logger.warning("Safety time limit exceeded")
                break

            try:
                self.store.set_phase(phase_name, "running")
                if phase_name == "planning":
                    result = await self.surface.planning(query=query, run_id=run_id)
                    # Extract search queries from plan
                    if hasattr(result, "artifacts") and result.artifacts:
                        plan = result.artifacts[0].payload
                        for sq in plan.get("sub_questions", []):
                            plan_queries.append({
                                "question": sq.get("question", ""),
                                "query": sq.get("search_query", sq.get("question", "")),
                                "sources": sq.get("search_sources", ["general"]),
                            })
                elif phase_name == "knowledge_retrieval":
                    result = await self.surface.knowledge_retrieval(query=query, run_id=run_id)
                    if hasattr(result, "artifacts") and result.artifacts:
                        rag_evidence = result.artifacts[0].payload.get("existing_evidence", [])
                elif phase_name == "evidence_acquisition":
                    result = await self.surface.evidence_acquisition(
                        run_id=run_id, queries=plan_queries,
                        existing_evidence_count=len(rag_evidence),
                    )
                elif phase_name == "evidence_extraction":
                    result = await self.surface.evidence_extraction(
                        run_id=run_id, evidence_records=list(all_evidence),
                    )
                elif phase_name == "synthesis":
                    result = await self.surface.synthesis(
                        query=query, run_id=run_id, evidence_records=list(all_evidence),
                    )
                elif phase_name == "knowledge_upsert":
                    result = await self.surface.knowledge_upsert(
                        run_id=run_id, evidence_records=list(all_evidence),
                    )

                self.store.set_phase(phase_name, "succeeded")
                completed_phases.append(phase_name)

                if hasattr(result, "evidence"):
                    all_evidence.extend(result.evidence)
                if phase_name == "synthesis" and hasattr(result, "artifacts") and result.artifacts:
                    final_report = result.artifacts[0].payload
            except Exception as e:
                logger.error("Phase %s failed: %s", phase_name, e)
                self.store.set_phase(phase_name, "failed", error=str(e))

        # Gate 7: Delivery
        delivery_gate = check_delivery_gate(final_report)
        if not delivery_gate.passed:
            final_report["delivery_note"] = delivery_gate.feedback

        return {
            "status": "completed",
            "run_id": run_id,
            "report": final_report,
            "evidence_count": len(all_evidence),
            "phases_completed": completed_phases,
        }
