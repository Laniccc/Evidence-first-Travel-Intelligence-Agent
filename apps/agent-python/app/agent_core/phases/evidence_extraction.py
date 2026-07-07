"""Phase 4: Evidence Extraction — fetch web pages and extract claims via LLM."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import PhaseToolResult

logger = logging.getLogger(__name__)


async def run_evidence_extraction(
    store,
    run_id: str | None = None,
    topic_id: str | None = None,
    evidence_records: list[Any] | None = None,
    llm_client: Any = None,
    tool_registry: Any = None,
    sub_question_count: int = 2,
) -> PhaseToolResult:
    """Fetch web pages and extract key claims using LLM."""
    evidence_records = evidence_records or []

    for ev in evidence_records[:5]:
        url = ev.source_url
        if not url:
            continue

        content = await _fetch_page(tool_registry, url)
        store.append_job(
            phase_name="evidence_extraction", topic_id=topic_id,
            tool_name="mcp_fetch_web",
            status="succeeded" if content else "failed",
            input={"url": url},
        )

        if not content:
            continue

        if llm_client:
            claims = await _extract_claims_llm(llm_client, content, ev.source_name)
        else:
            claims = [{"claim": content[:300], "type": "snippet"}]

        # Update evidence with extracted claims (via raw_payload)
        ev.claims = claims

    artifact = await complete_phase_with_artifact(
        store, phase_name="evidence_extraction", topic_id=topic_id,
        artifact_type="evidence_extraction",
        payload={
            "processed_count": len(evidence_records),
            "total_claims": sum(len(getattr(e, "claims", []) or []) for e in evidence_records),
        },
        evidence_refs=[getattr(e, "evidence_id", "") for e in evidence_records],
    )
    return PhaseToolResult(artifacts=[artifact])


async def _fetch_page(tool_registry: Any, url: str) -> str | None:
    if tool_registry is None:
        return None
    try:
        if hasattr(tool_registry, "run_tool"):
            result = await tool_registry.run_tool("fetch_web", url=url, timeout=10000)
            return result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url, e)
    return None


async def _extract_claims_llm(llm_client: Any, content: str, source_name: str) -> list[dict[str, Any]]:
    truncated = content[:4000]
    prompt = f"""Extract 3-5 key factual claims from this article.
Article from: {source_name}
Content: {truncated}

Respond as JSON: {{"claims": [{{"claim": "...", "type": "fact"}}]}}"""
    try:
        text = await llm_client.complete(
            system="Extract ONLY factual claims from articles. Output valid JSON.",
            user=prompt,
            max_tokens=1024,
            json_only=True,
        )
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group()).get("claims", [])
    except Exception as e:
        logger.warning("LLM extraction failed: %s", e)
    return [{"claim": content[:200], "type": "snippet"}]
