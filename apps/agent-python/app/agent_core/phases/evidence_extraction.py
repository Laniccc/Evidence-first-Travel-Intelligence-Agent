"""Phase 4: Evidence Extraction — fetch web pages and extract claims via LLM."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from app.agent_core.contracts.gate_checks import classify_source_tier
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
    fetched_ok = 0
    fetched_fail = 0
    total_claims = 0
    evidence_with_claims = 0

    # Sort evidence: direct URLs first, then by tier (T1 before T3), then preserve original order
    def _sort_key(ev: Any) -> tuple[int, int, int]:
        tier = 3
        is_direct = 0
        if hasattr(ev, "raw_payload") and isinstance(ev.raw_payload, dict):
            tier = ev.raw_payload.get("source_tier", 3)
            if ev.raw_payload.get("source_type") == "direct":
                is_direct = -1  # Direct URLs come first
        return (is_direct, tier, 0)

    sorted_evidence = sorted(evidence_records, key=_sort_key)

    for ev in sorted_evidence[:8]:
        url = ev.source_url
        if not url:
            continue

        # Resolve redirect URLs BEFORE fetching
        real_url = _resolve_redirect_url(url)
        if real_url and _is_search_redirect(url):
            ev.source_url = real_url
            real_tier = classify_source_tier(real_url, title_hint=ev.source_name)
            ev.source_tier = real_tier
            if hasattr(ev, "raw_payload") and isinstance(ev.raw_payload, dict):
                ev.raw_payload["source_tier"] = real_tier
            logger.info("Resolved redirect → %s (T%d)", real_url, real_tier)
            url = real_url

        content = await _fetch_page(tool_registry, url, timeout=25000)

        # Fallback: extract real URL from fetched content
        if not real_url:
            real_url = _extract_real_url(content)
            if real_url and _is_search_redirect(url):
                ev.source_url = real_url
                real_tier = classify_source_tier(real_url, title_hint=ev.source_name)
                ev.source_tier = real_tier
                if hasattr(ev, "raw_payload") and isinstance(ev.raw_payload, dict):
                    ev.raw_payload["source_tier"] = real_tier
                url = real_url
                logger.info("Extracted real URL from content → %s (T%d)", real_url, real_tier)

        store.append_job(
            phase_name="evidence_extraction", topic_id=topic_id,
            tool_name="mcp_fetch_web",
            status="succeeded" if content else "failed",
            input={"url": url},
        )

        if not content:
            fetched_fail += 1
            continue

        fetched_ok += 1

        if llm_client:
            claims = await _extract_claims_llm(llm_client, content, ev.source_name)
        else:
            claims = [{"claim": content[:300], "type": "snippet"}]

        # Update evidence with extracted claims
        ev.claims = claims
        total_claims += len(claims or [])
        if claims and len(claims) > 0:
            evidence_with_claims += 1

    artifact = await complete_phase_with_artifact(
        store, phase_name="evidence_extraction", topic_id=topic_id,
        artifact_type="evidence_extraction",
        payload={
            "processed_count": len(evidence_records),
            "fetched_ok": fetched_ok,
            "fetched_fail": fetched_fail,
            "total_claims": total_claims,
            "evidence_with_claims": evidence_with_claims,
        },
        evidence_refs=[getattr(e, "evidence_id", "") for e in evidence_records],
    )
    return PhaseToolResult(artifacts=[artifact])


async def _fetch_page(tool_registry: Any, url: str, timeout: int = 15000) -> str | None:
    if tool_registry is None:
        return None
    try:
        if hasattr(tool_registry, "run_tool"):
            result = await tool_registry.run_tool("fetch_web", url=url, timeout=timeout)
            return result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.warning("Fetch failed for %s: %s", url[:80], e)
    return None


def _is_search_redirect(url: str) -> bool:
    """Check if URL is a search-engine redirect that needs resolution."""
    try:
        domain = urlparse(url).netloc.lower()
        return any(k in domain for k in ("baidu.com", "sogou.com"))
    except Exception:
        return False


def _resolve_redirect_url(url: str, timeout: int = 5) -> str | None:
    """Follow HTTP redirect to get the real destination URL.

    Uses a lightweight HEAD request that follows redirects via urllib.
    Returns the final URL after all redirects, or None if resolution fails.
    """
    import urllib.request
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent",
                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        resp = urllib.request.urlopen(req, timeout=timeout)
        final_url = resp.geturl()
        resp.close()
        if final_url != url and not _is_search_redirect(final_url):
            return final_url
    except Exception:
        pass
    return None


def _extract_real_url(content: str | None) -> str | None:
    """Extract the real page URL from fetched page content.

    Checks raw HTML canonical/og:url tags and also searches for
    https:// URLs that look like article sources in text content.
    """
    if not content:
        return None
    # canonical link (raw HTML)
    m = re.search(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)', content)
    if not m:
        m = re.search(r'<meta\s+property=["\']og:url["\']\s+content=["\']([^"\']+)', content)
    if not m:
        # Text extracted by fetch-web — look for source URL patterns
        m = re.search(r'(?:原文链接|原文|来源|source|from|via|Original)\s*[:：]\s*(https?://[^\s\n]+)', content)
    if not m:
        # Last resort: find first plausible article URL in text
        m = re.search(r'https?://(?!www\.baidu\.com|link\?url=)([a-zA-Z0-9][^\s\n]{10,})', content)
    if m:
        url = m.group(1).strip() if "://" in m.group(1) else m.group().strip()
        if url.startswith("http") and not _is_search_redirect(url):
            return url
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
