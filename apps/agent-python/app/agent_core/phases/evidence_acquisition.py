"""Phase 3: Evidence Acquisition — search the web for information on knowledge gaps."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.agent_core.contracts.gate_checks import check_source_gate, classify_source_tier
from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import PhaseToolResult

logger = logging.getLogger(__name__)

# Domains known to be search-engine redirects — real URL must be resolved
REDIRECT_DOMAINS = {"baidu.com", "sogou.com"}


def _is_redirect_url(url: str) -> bool:
    """Check if a URL is a search-engine redirect link."""
    try:
        return urlparse(url).netloc.split(".")[-2:] in [
            ["baidu", "com"], ["sogou", "com"],
        ]
    except Exception:
        return False


async def run_evidence_acquisition(
    store,
    run_id: str | None = None,
    topic_id: str | None = None,
    queries: list[dict[str, str]] | None = None,
    tool_registry: Any = None,
    existing_evidence_count: int = 0,
    direct_urls: list[str] | None = None,
    retry_round: int = 1,
) -> PhaseToolResult:
    """Search the web for information and inject known source URLs directly.

    retry_round: 1 = initial search, 2 = refined search from sufficiency gaps.
    On round 2, search queries are presumed to be more targeted fills for gaps.
    """
    queries = queries or []
    direct_urls = direct_urls or [] if retry_round == 1 else []  # Only direct URLs on round 1
    evidence_records = []
    job_records = []

    if existing_evidence_count >= len(queries) * 2 and not direct_urls:
        artifact = await complete_phase_with_artifact(
            store, phase_name="evidence_acquisition", topic_id=topic_id,
            artifact_type="evidence_acquisition",
            payload={"search_skipped": True, "reason": "knowledge_base_sufficient"},
        )
        return PhaseToolResult(artifacts=[artifact], evidence=evidence_records)

    # Inject direct URLs as evidence first (no search needed)
    for url in direct_urls:
        tier = classify_source_tier(url)  # No redirect for direct URLs
        ev = store.append_evidence(
            source_name=url.split("/")[-1] or url,
            source_type="direct",
            source_url=url,
            topic_id=topic_id,
            source_tier=tier,
            raw_payload={
                "snippet": f"Direct fetch: {url}",
                "source_tier": tier,
                "needs_url_resolution": False,
            },
        )
        evidence_records.append(ev)
        logger.info("Direct URL added: %s (T%d)", url, tier)

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
            title = r.get("title", url)
            tier = classify_source_tier(url, title_hint=title)
            if tier >= 5:
                continue
            ev = store.append_evidence(
                source_name=title,
                source_type=r.get("engine", "web"),
                source_url=url,
                topic_id=topic_id,
                source_tier=tier,
                raw_payload={
                    "snippet": r.get("description", ""),
                    "source_tier": tier,
                    "needs_url_resolution": _is_redirect_url(url),
                    **r,
                },
            )
            evidence_records.append(ev)

    artifact = await complete_phase_with_artifact(
        store, phase_name="evidence_acquisition", topic_id=topic_id,
        artifact_type="evidence_acquisition",
        payload={
            "evidence_count": len(evidence_records),
            "retry_round": retry_round,
            "direct_url_count": len(direct_urls),
            "search_query_count": len(queries),
        },
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
