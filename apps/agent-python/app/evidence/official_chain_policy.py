"""Official discovery / page-reader preconditions for S5."""

from __future__ import annotations

import importlib
from typing import Any

from app.evidence.official_candidate_bridge import has_readable_url_inputs


def collect_search_urls_for_claim(state: Any, claim_type: str | None = None) -> list[str]:
    """Harvest candidate URLs from search evidence for official discovery."""
    urls: list[str] = []
    for evidence in getattr(state, "evidence", None) or []:
        url = str(getattr(evidence, "source_url", "") or "").strip()
        if url.startswith("http") and url not in urls:
            urls.append(url)
    structured = getattr(state, "structured_result", None) or {}
    for row in structured.get("keyword_search_results") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("link") or "").strip()
        if url.startswith("http") and url not in urls:
            urls.append(url)
    return urls


def can_call_official_discovery(state: Any, claim_type: str | None = None) -> bool:
    return bool(collect_search_urls_for_claim(state, claim_type))


def can_call_official_page_reader(state: Any, claim_type: str | None = None) -> bool:
    return has_readable_url_inputs(state, claim_type)


def skip_official_discovery_if_no_urls(
    state: Any,
    *,
    claim_type: str | None = None,
) -> bool:
    if can_call_official_discovery(state, claim_type):
        return False
    reason = "no_urls_or_search_results"
    _record_skip(state, "official_source", reason, claim_type=claim_type)
    return True


def skip_official_page_reader_if_no_candidate(
    state: Any,
    *,
    claim_type: str | None = None,
) -> bool:
    if can_call_official_page_reader(state, claim_type):
        return False
    reason = "no_official_candidate_url"
    _record_skip(state, "official_page_reader", reason, claim_type=claim_type)
    return True


def has_search_url_inputs(state: Any) -> bool:
    return bool(collect_search_urls_for_claim(state))


def _record_skip(state: Any, family: str, reason: str, *, claim_type: str | None) -> None:
    record_skip = importlib.import_module(
        "app.execution.retrieval_attempt_ledger"
    ).record_skip
    record_skip(state, family, reason, claim_type=claim_type)
