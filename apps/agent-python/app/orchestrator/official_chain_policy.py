"""Official discovery / page-reader preconditions for S5."""

from __future__ import annotations

from app.orchestrator.official_candidate_bridge import has_readable_url_inputs
from app.orchestrator.retrieval_attempt_ledger import record_skip
from app.orchestrator.ticket_lookup_helpers import collect_ticket_search_urls, has_ticket_url_inputs
from app.schemas.user_query import TravelAgentState


def collect_search_urls_for_claim(state: TravelAgentState, claim_type: str | None = None) -> list[str]:
    """Harvest candidate URLs from search evidence for official discovery."""
    return collect_ticket_search_urls(state)


def can_call_official_discovery(state: TravelAgentState, claim_type: str | None = None) -> bool:
    return has_ticket_url_inputs(state)


def can_call_official_page_reader(state: TravelAgentState, claim_type: str | None = None) -> bool:
    return has_readable_url_inputs(state, claim_type)


def skip_official_discovery_if_no_urls(
    state: TravelAgentState,
    *,
    claim_type: str | None = None,
) -> bool:
    if can_call_official_discovery(state, claim_type):
        return False
    reason = "no_urls_or_search_results"
    record_skip(state, "official_source", reason, claim_type=claim_type)
    return True


def skip_official_page_reader_if_no_candidate(
    state: TravelAgentState,
    *,
    claim_type: str | None = None,
) -> bool:
    if can_call_official_page_reader(state, claim_type):
        return False
    reason = "no_official_candidate_url"
    record_skip(state, "official_page_reader", reason, claim_type=claim_type)
    return True


def has_search_url_inputs(state: TravelAgentState) -> bool:
    return has_ticket_url_inputs(state)