"""Phase 3: Evidence Acquisition — search the web for information on knowledge gaps."""

from __future__ import annotations

import logging
from typing import Any

from app.agent_core.contracts.gate_checks import check_source_gate, classify_source_tier
from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import PhaseToolResult

logger = logging.getLogger(__name__)


async def run_evidence_acquisition(
    store,
    run_id: str | None = None,
    topic_id: str | None = None,
    queries: list[dict[str, str]] | None = None,
    tool_registry: Any = None,
    existing_evidence_count: int = 0,
) -> PhaseToolResult:
    """Search the web for information, focusing only on knowledge gaps."""
    queries = queries or []
    evidence_records = []
    job_records = []

    if existing_evidence_count >= len(queries) * 2:
        artifact = await complete_phase_with_artifact(
            store, phase_name="evidence_acquisition", topic_id=topic_id,
            artifact_type="evidence_acquisition",
            payload={"search_skipped": True, "reason": "knowledge_base_sufficient"},
        )
        return PhaseToolResult(artifacts=[artifact], evidence=evidence_records)

    for query_info in queries[:10]:
        search_query = query_info.get("query", query_info.get("question", ""))
        if not search_query:
            continue

        results = await _execute_search(tool_registry, search_query)

        store.append_job(
            phase_name="evidence_acquisition", topic_id=topic_id,
            tool_name="mcp_search",
            status="succeeded" if results else "failed",
            input={"query": search_query},
        )

        for r in results:
            url = r.get("url", "")
            tier = classify_source_tier(url)
            if tier >= 5:
                continue
            ev = store.append_evidence(
                source_name=r.get("title", url),
                source_type=r.get("engine", "web"),
                source_url=url,
                topic_id=topic_id,
                raw_payload={"snippet": r.get("description", ""), "source_tier": tier, **r},
            )
            evidence_records.append(ev)

    artifact = await complete_phase_with_artifact(
        store, phase_name="evidence_acquisition", topic_id=topic_id,
        artifact_type="evidence_acquisition",
        payload={"evidence_count": len(evidence_records)},
        evidence_refs=[e.evidence_id for e in evidence_records],
    )
    return PhaseToolResult(artifacts=[artifact], evidence=evidence_records)


async def _execute_search(tool_registry: Any, query: str) -> list[dict[str, Any]]:
    if tool_registry is None:
        return []
    try:
        if hasattr(tool_registry, "run_tool"):
            result = await tool_registry.run_tool("search", query=query, limit=5)
            return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning("Search failed: %s", e)
    return []
