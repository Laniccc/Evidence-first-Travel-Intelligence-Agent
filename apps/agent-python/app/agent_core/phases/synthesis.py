"""Phase 5: Synthesis — compose research report with citations."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agent_core.contracts.gate_checks import check_citation_gate, check_crossref_gate
from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import CrossReferenceResult, PhaseToolResult

logger = logging.getLogger(__name__)


async def run_synthesis(
    store,
    query: str,
    run_id: str | None = None,
    topic_id: str | None = None,
    evidence_records: list[Any] | None = None,
    llm_client: Any = None,
) -> PhaseToolResult:
    """Synthesize evidence into a structured research report."""
    evidence_records = evidence_records or []

    # Cross-reference
    cross_refs = _cross_reference(evidence_records)

    # Generate report
    citations = [
        {"id": i + 1, "title": getattr(e, "source_name", ""), "url": getattr(e, "source_url", ""),
         "tier": getattr(e, "source_tier", 3)}
        for i, e in enumerate(evidence_records)
    ]

    if llm_client and evidence_records:
        report = await _generate_llm(llm_client, query, evidence_records, citations)
    else:
        report = _generate_fallback(query, evidence_records, citations)

    # Gate 5: Cross-ref (non-blocking)
    cr_gate = check_crossref_gate([cr.model_dump() for cr in cross_refs])
    if not cr_gate.passed:
        report["limitations"] = report.get("limitations", []) + [cr_gate.feedback]

    # Gate 6: Citation (non-blocking)
    cit_gate = check_citation_gate(report.get("sections", []), citations)
    if not cit_gate.passed:
        report["limitations"] = report.get("limitations", []) + [cit_gate.feedback]

    artifact = await complete_phase_with_artifact(
        store, phase_name="synthesis", topic_id=topic_id,
        artifact_type="research_report", payload=report,
        evidence_refs=[getattr(e, "evidence_id", "") for e in evidence_records],
    )
    return PhaseToolResult(artifacts=[artifact])


def _cross_reference(evidence: list[Any]) -> list[CrossReferenceResult]:
    results = []
    for ev in evidence:
        status = "unverified"
        if len(getattr(ev, "claims", []) or []) >= 2:
            status = "verified"
        results.append(CrossReferenceResult(
            claim=getattr(ev, "source_name", "")[:100],
            source_refs=[getattr(ev, "source_url", "")],
            corroborating_sources=min(len(getattr(ev, "claims", []) or []), 3),
            status=status,
        ))
    return results


async def _generate_llm(llm_client, query, evidence, citations) -> dict[str, Any]:
    evidence_text = ""
    for i, ev in enumerate(evidence, 1):
        claims = [c.get("claim", str(c)) if isinstance(c, dict) else str(c) for c in (getattr(ev, "claims", []) or [])]
        evidence_text += f"[{i}] {getattr(ev, 'source_name', '')}\n" + "\n".join(f"  - {c}" for c in claims[:3]) + "\n\n"

    prompt = f"""Write a structured research report using ONLY the provided evidence. Reference sources with [N].

Topic: {query}

Evidence:
{evidence_text[:6000]}

Respond as JSON: {{"title": "...", "summary": "...", "sections": [{{"type": "findings", "heading": "...", "content": "..."}}], "limitations": ["..."]}}"""

    try:
        text = await llm_client.complete(
            system="You are a research analyst. Write structured reports using ONLY provided evidence. Cite sources with [N]. Output valid JSON only.",
            user=prompt,
            max_tokens=2048,
            json_only=True,
        )
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            data["citations"] = citations
            data["word_count"] = len(data.get("summary", ""))
            return data
    except Exception as e:
        logger.warning("LLM synthesis failed: %s", e)
    return _generate_fallback(query, evidence, citations)


def _generate_fallback(query, evidence, citations) -> dict[str, Any]:
    return {
        "title": f"Research: {query[:60]}",
        "summary": f"Found {len(evidence)} sources. Synthesis requires LLM.",
        "sections": [{"type": "findings", "heading": "Sources", "content": "\n".join(f"- {getattr(e, 'source_name', '')}" for e in evidence[:5])}],
        "citations": citations,
        "limitations": ["No LLM synthesis — showing raw sources"],
        "word_count": 0,
    }
