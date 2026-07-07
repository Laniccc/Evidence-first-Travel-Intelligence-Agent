"""Shared helpers for research agent phases."""

from __future__ import annotations

import logging
from typing import Any

from app.agent_core.state.ids import generate_artifact_id as make_artifact_id
from app.agent_core.state.models import ArtifactRecord

logger = logging.getLogger(__name__)


async def complete_phase_with_artifact(
    store,
    phase_name: str,
    artifact_type: str,
    payload: dict[str, Any],
    evidence_refs: list[str] | None = None,
    *,
    topic_id: str | None = None,
    created_by: str = "system",
) -> ArtifactRecord:
    """Standard lifecycle: create artifact and approve it.

    Returns the created ArtifactRecord.
    """
    artifact = store.append_artifact(
        phase_name=phase_name,
        artifact_type=artifact_type,
        status="approved",
        topic_id=topic_id,
        payload=payload,
        evidence_refs=evidence_refs or [],
        created_by=created_by,
    )
    return artifact


def extract_search_queries(plan: dict[str, Any]) -> list[dict[str, str]]:
    """Extract search queries from a research plan."""
    queries = []
    for q in plan.get("sub_questions", []):
        queries.append({
            "question": q.get("question", ""),
            "query": q.get("search_query", ""),
            "sources": q.get("search_sources", ["general"]),
        })
    return queries


def format_report_markdown(report: dict[str, Any]) -> str:
    """Format a research report as Markdown."""
    md = f"# {report.get('title', 'Research Report')}\n\n"
    md += f"## Summary\n\n{report.get('summary', '')}\n\n"

    for section in report.get("sections", []):
        md += f"## {section.get('heading', 'Section')}\n\n"
        md += f"{section.get('content', '')}\n\n"

    md += "## Sources\n\n"
    for i, c in enumerate(report.get("citations", []), 1):
        tier_label = c.get("tier_label", "")
        md += f"{i}. [{c.get('title', 'Source')}]({c.get('url', '')})"
        if tier_label:
            md += f" — {tier_label}"
        md += "\n"

    if report.get("limitations"):
        md += "\n## Limitations\n\n"
        for lim in report["limitations"]:
            md += f"- {lim}\n"

    return md
