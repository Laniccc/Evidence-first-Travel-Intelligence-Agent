"""Root supervisor for the Research Agent pipeline — self-aware agent loop."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agent_core.contracts.gate_checks import (
    check_citation_gate,
    check_crossref_gate,
    check_delivery_gate,
    check_evidence_gate,
    check_evidence_sufficiency,
    check_input_gate,
    check_plan_gate,
    check_source_gate,
)
from app.agent_core.gate import PipelineGate
from app.agent_core.state.lifecycle import FULL_PHASE_ORDER
from app.agent_core.store import AgentCoreStore
from app.agent_core.supervisor_policy import AgentCoreSupervisorPolicy
from app.agent_core.tool_surface import AgentCoreToolSurface
from app.debug_session_log import write_debug_session
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

SAFETY_LIMITS = {
    "max_run_duration_seconds": 300,
    "max_evidence_rounds": 2,
}


class AgentCoreSupervisor:
    """Self-aware supervisor: searches, evaluates evidence, retries if insufficient."""

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
        self.llm_client = llm_client
        self.rag_store = rag_store
        self.gate = PipelineGate()
        self.policy = AgentCoreSupervisorPolicy()
        self.skills = SkillRegistry()
        self._started_at = time.time()

    # ── public entry point ──────────────────────────────────────────────────

    async def run(self, *, query: str, user_context: dict | None = None) -> dict[str, Any]:
        """Execute the full research pipeline with evidence sufficiency checks."""
        started_at = time.time()

        # ═══ Gate 1: Input (ONLY hard gate) ═══
        input_result = check_input_gate(query)
        if input_result.action == "return_to_user":
            return {"status": "clarification_needed", "message": input_result.feedback}

        # ═══ Ingress + Skill Selection ═══
        run_id = self.surface.ingress(query=query, user_context=user_context)
        completed_phases: list[str] = []
        gate_results: dict[str, Any] = {}
        all_errors: list[str] = []

        # Select relevant skills based on query
        selected_skills = self.skills.select_for_query(query)
        skills_prompt = self.skills.render_prompt_block(selected_skills)
        logger.info("Activated skills: %s", [s.name for s in selected_skills])

        # ═══ Phase 1: Planning + Gate 2 ═══
        plan_result = await self.surface.planning(
            query=query, run_id=run_id, skills_prompt=skills_prompt,
        )
        completed_phases.append("planning")

        plan_queries, direct_urls = self._extract_plan(plan_result)
        plan_gate = check_plan_gate(plan_queries)
        gate_results["plan"] = plan_gate
        if not plan_gate.passed:
            all_errors.append(f"Gate 2 (plan): {plan_gate.feedback}")

        # ═══ Phase 2: Knowledge Retrieval ═══
        rag_evidence: list[dict] = []
        try:
            kr_result = await self.surface.knowledge_retrieval(query=query, run_id=run_id)
            completed_phases.append("knowledge_retrieval")
            if hasattr(kr_result, "artifacts") and kr_result.artifacts:
                rag_evidence = kr_result.artifacts[0].payload.get("existing_evidence", [])
        except Exception as e:
            logger.warning("Knowledge retrieval failed (non-blocking): %s", e)

        # ═══ Evidence Round Loop (max 2) ═══
        all_evidence: list[Any] = []
        round_num = 1
        sufficient = False
        sufficiency_result: dict[str, Any] = {}
        rounds_detail: list[dict] = []

        while round_num <= SAFETY_LIMITS["max_evidence_rounds"]:
            if time.time() - started_at > SAFETY_LIMITS["max_run_duration_seconds"]:
                logger.warning("Safety time limit exceeded at round %d", round_num)
                all_errors.append("Time limit exceeded")
                break

            round_info = await self._run_evidence_round(
                run_id=run_id,
                plan_queries=plan_queries,
                direct_urls=direct_urls,
                all_evidence=all_evidence,
                rag_evidence=rag_evidence,
                round_num=round_num,
                sufficiency_result=sufficiency_result,
                query=query,
            )
            rounds_detail.append(round_info)

            # Update phase tracking
            if "evidence_acquisition" not in completed_phases:
                completed_phases.append("evidence_acquisition")
            if "evidence_extraction" not in completed_phases:
                completed_phases.append("evidence_extraction")

            # Check sufficiency
            sufficiency_result = await check_evidence_sufficiency(
                query, list(all_evidence), self.llm_client,
            )
            sufficient = sufficiency_result.get("sufficient", False)
            gate_results[f"sufficiency_r{round_num}"] = sufficiency_result

            logger.info(
                "Round %d sufficiency: %s (confidence %.2f, gaps: %d)",
                round_num, "SUFFICIENT" if sufficient else "INSUFFICIENT",
                sufficiency_result.get("confidence", 0),
                len(sufficiency_result.get("gaps", [])),
            )

            if sufficient:
                break

            if round_num < SAFETY_LIMITS["max_evidence_rounds"]:
                logger.info(
                    "Insufficient — retrying with refined queries: %s",
                    sufficiency_result.get("suggested_queries", []),
                )
                # Use refined queries from sufficiency check for next round
                refined = sufficiency_result.get("suggested_queries", [])
                if refined:
                    plan_queries = [{"query": q, "question": q, "sources": ["general"]} for q in refined]
                direct_urls = []  # Only direct URLs on round 1
                round_num += 1
            else:
                break

        # ═══ Post-evidence decision ═══
        if not sufficient or len(all_evidence) == 0:
            # ABORT: cannot answer
            abort_report = self._build_abort_report(query, all_evidence, sufficiency_result, all_errors)
            result = {
                "status": "insufficient_evidence",
                "run_id": run_id,
                "report": abort_report,
                "evidence_count": len(all_evidence),
                "phases_completed": completed_phases,
                "errors": all_errors,
                "rounds": rounds_detail,
                "_evidence_detail": self._collect_evidence_detail(all_evidence),
            }
            try:
                write_debug_session(query=query, result=result)
            except Exception:
                pass
            return result

        # ═══ Phase 5: Synthesis + Gates 5-6 ═══
        try:
            synth_result = await self.surface.synthesis(
                query=query, run_id=run_id, evidence_records=list(all_evidence),
                skills_prompt=skills_prompt,
            )
            completed_phases.append("synthesis")
            final_report = synth_result.artifacts[0].payload if hasattr(synth_result, "artifacts") and synth_result.artifacts else {}
        except Exception as e:
            logger.error("Synthesis failed: %s", e)
            all_errors.append(f"synthesis: {e}")
            final_report = self._build_abort_report(query, all_evidence, sufficiency_result, all_errors)

        # Gate 7: Delivery
        delivery_gate = check_delivery_gate(final_report)
        gate_results["delivery"] = delivery_gate
        if not delivery_gate.passed:
            final_report["delivery_note"] = delivery_gate.feedback

        # ═══ Phase 6: Knowledge Upsert (quality-gated) ═══
        quality_evidence = [
            e for e in all_evidence
            if getattr(e, "source_tier", 3) <= 3 and len(getattr(e, "claims", []) or []) > 0
        ]
        if quality_evidence:
            try:
                await self.surface.knowledge_upsert(
                    run_id=run_id, evidence_records=quality_evidence,
                )
                completed_phases.append("knowledge_upsert")
                logger.info("RAG upsert: %d/%d records stored (quality-filtered)", len(quality_evidence), len(all_evidence))
            except Exception as e:
                logger.warning("Knowledge upsert failed (non-blocking): %s", e)
        else:
            logger.warning("RAG upsert SKIPPED: no evidence passed quality filter (T<=3, claims>=1)")

        # ═══ Build result ═══
        result = {
            "status": "completed",
            "run_id": run_id,
            "report": final_report,
            "evidence_count": len(all_evidence),
            "quality_evidence_count": len(quality_evidence),
            "phases_completed": completed_phases,
            "errors": all_errors,
            "gate_results": {k: _serialize_gate(v) for k, v in gate_results.items()},
            "rounds": rounds_detail,
            "_evidence_detail": self._collect_evidence_detail(all_evidence),
        }

        try:
            write_debug_session(query=query, result=result)
        except Exception as e:
            logger.warning("Failed to write debug session: %s", e)

        return result

    # ── helpers ─────────────────────────────────────────────────────────────

    def _extract_plan(self, plan_result: Any) -> tuple[list[dict], list[str]]:
        """Extract search queries and direct URLs from planning result."""
        queries: list[dict] = []
        direct_urls: list[str] = []
        if hasattr(plan_result, "artifacts") and plan_result.artifacts:
            plan = plan_result.artifacts[0].payload
            for sq in plan.get("sub_questions", []):
                queries.append({
                    "question": sq.get("question", ""),
                    "query": sq.get("search_query", sq.get("question", "")),
                    "sources": sq.get("search_sources", ["general"]),
                })
                for u in sq.get("direct_urls", []):
                    if u not in direct_urls:
                        direct_urls.append(u)
        return queries, direct_urls

    async def _run_evidence_round(
        self,
        *,
        run_id: str,
        plan_queries: list[dict],
        direct_urls: list[str],
        all_evidence: list,
        rag_evidence: list[dict],
        round_num: int,
        sufficiency_result: dict,
        query: str,
    ) -> dict:
        """Execute one round of evidence acquisition + extraction."""
        round_detail: dict[str, Any] = {
            "round": round_num,
            "queries_used": [q.get("query", "") for q in plan_queries],
            "acquisition_count": 0,
            "extraction_stats": {},
            "errors": [],
        }

        # Phase 3: Evidence Acquisition
        try:
            acq_result = await self.surface.evidence_acquisition(
                run_id=run_id,
                queries=plan_queries,
                existing_evidence_count=len(all_evidence) + len(rag_evidence),
                direct_urls=direct_urls,
                retry_round=round_num,
            )
            if hasattr(acq_result, "evidence"):
                new_evidence = acq_result.evidence
            else:
                new_evidence = []
            all_evidence.extend(new_evidence)
        except Exception as e:
            logger.error("Evidence acquisition round %d failed: %s", round_num, e)
            round_detail["errors"].append(f"acquisition: {e}")
            return round_detail

        round_detail["acquisition_count"] = len(new_evidence)

        # Gate 3: Source quality
        source_gate = check_source_gate(
            [{"url": getattr(e, "source_url", ""), "title": getattr(e, "source_name", "")} for e in new_evidence],
        )
        if not source_gate.passed:
            logger.warning("Gate 3 (source): %s", source_gate.feedback)
            round_detail["errors"].append(f"source_gate: {source_gate.feedback}")

        # Phase 4: Evidence Extraction
        try:
            ext_result = await self.surface.evidence_extraction(
                run_id=run_id, evidence_records=list(all_evidence),
            )
            if hasattr(ext_result, "artifacts") and ext_result.artifacts:
                round_detail["extraction_stats"] = ext_result.artifacts[0].payload
        except Exception as e:
            logger.error("Evidence extraction round %d failed: %s", round_num, e)
            round_detail["errors"].append(f"extraction: {e}")

        # Gate 4: Evidence sufficiency (count-based pre-check)
        evidence_gate = check_evidence_gate(
            [{"claims": getattr(e, "claims", []) or []} for e in new_evidence],
            len(plan_queries),
        )
        if not evidence_gate.passed:
            logger.warning("Gate 4 (evidence): %s", evidence_gate.feedback)
            round_detail["errors"].append(f"evidence_gate: {evidence_gate.feedback}")

        return round_detail

    def _build_abort_report(
        self,
        query: str,
        evidence: list,
        sufficiency: dict,
        errors: list,
    ) -> dict[str, Any]:
        """Build an honest 'cannot answer' report when evidence is insufficient."""
        gaps = sufficiency.get("gaps", [])
        reasoning = sufficiency.get("reasoning", "Insufficient evidence after max rounds")
        citations = [
            {"id": i + 1, "title": getattr(e, "source_name", ""), "url": getattr(e, "source_url", ""),
             "tier": getattr(e, "source_tier", 3)}
            for i, e in enumerate(evidence)
        ]
        return {
            "title": f"Unable to answer: {query[:60]}",
            "summary": f"After {SAFETY_LIMITS['max_evidence_rounds']} search rounds, the agent could not find sufficient evidence to answer this question. {reasoning}",
            "sections": [
                {"type": "findings", "heading": "What was found",
                 "content": f"{len(evidence)} sources were discovered, but none contained enough specific information to answer the query."},
                {"type": "analysis", "heading": "Knowledge Gaps",
                 "content": "\n".join(f"- {g}" for g in gaps) if gaps else "Unable to identify specific gaps."},
            ],
            "citations": citations,
            "limitations": [
                reasoning,
                *gaps,
                *[e for e in errors[-3:]],
            ],
            "word_count": 0,
        }

    def _collect_evidence_detail(self, evidence: list) -> list[dict]:
        """Collect summary fields from evidence records for debug output."""
        detail: list[dict] = []
        for ev in evidence:
            d: dict[str, Any] = {}
            if hasattr(ev, "source_name"):
                d["source_name"] = ev.source_name
            if hasattr(ev, "source_url"):
                d["source_url"] = ev.source_url
            if hasattr(ev, "source_tier"):
                d["source_tier"] = ev.source_tier
            if hasattr(ev, "source_type"):
                d["source_type"] = ev.source_type
            if d:
                detail.append(d)
        return detail


def _serialize_gate(value: Any) -> dict:
    """Serialize a GateResult or dict to a consistent dict for output."""
    if isinstance(value, dict):
        return {"passed": value.get("sufficient", value.get("passed", False)),
                "feedback": value.get("reasoning", value.get("feedback", ""))}
    return {"passed": getattr(value, "passed", False),
            "feedback": getattr(value, "feedback", "")}
