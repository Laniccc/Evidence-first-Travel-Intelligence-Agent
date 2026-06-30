"""Track ticket_price lookup attempts — thin wrapper over retrieval_attempt_ledger."""

from __future__ import annotations

import re

from app.orchestrator.fact_lookup_policy import is_fact_lookup_task, primary_fact_need_from_state
from app.orchestrator.retrieval_attempt_ledger import (
    get_ledger,
    record_official_discovery_skipped,
    record_skip,
    retrieval_complete as _retrieval_complete,
    save_ledger,
    source_family_for_tool,
)
from app.orchestrator.ticket_lookup_helpers import has_ticket_url_inputs
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name

_SEARCH_SUBAGENTS = frozenset({"fact_search_agent", "keyword_search_agent", "fact_lookup_agent"})
_TICKET_PRICE_NEEDS = frozenset(
    {
        "ticket_price",
        "entrance_ticket_price",
        "boat_ticket_price",
        "shuttle_bus_ticket_price",
        "cable_car_ticket_price",
    }
)


def _structured(state: TravelAgentState) -> dict:
    return dict(state.structured_result or {})


def search_family_attempted(state: TravelAgentState) -> bool:
    ledger = get_ledger(state, "ticket_price")
    return "search" in ledger.families_attempted()


def official_family_attempted_or_skipped(state: TravelAgentState) -> bool:
    ledger = get_ledger(state, "ticket_price")
    return "official_source" in ledger.families_attempted()


def platform_family_attempted(state: TravelAgentState) -> bool:
    ledger = get_ledger(state, "ticket_price")
    return "ticket_platform" in ledger.families_attempted()


def map_family_attempted(state: TravelAgentState) -> bool:
    ledger = get_ledger(state, "ticket_price")
    return "map_candidate" in ledger.families_attempted()


def ticket_lookup_retrieval_complete_by_family(state: TravelAgentState) -> bool:
    if not is_fact_lookup_task(state):
        return False
    if primary_fact_need_from_state(state) not in _TICKET_PRICE_NEEDS:
        return False
    return _retrieval_complete(state, "ticket_price") and ticket_lookup_has_price_evidence(state)


def ticket_lookup_has_price_evidence(
    state: TravelAgentState,
    claim_type: str | None = None,
) -> bool:
    """Return True only when current evidence contains an extractable ticket amount."""
    need = claim_type or primary_fact_need_from_state(state) or "ticket_price"
    if need not in _TICKET_PRICE_NEEDS:
        need = "ticket_price"
    from app.orchestrator.ticket_price_extractor import extract_ticket_price_from_evidence

    if extract_ticket_price_from_evidence(list(state.evidence or []), claim_type=need):
        return True
    if need != "ticket_price":
        return bool(
            extract_ticket_price_from_evidence(list(state.evidence or []), claim_type="ticket_price")
        )
    return False


def normalize_subagent_objective(
    *,
    subagent: str,
    claim_type: str | None = None,
    lookup_phase: str | None = None,
    source_family: str | None = None,
    search_query: str | None = None,
    ticket_product: str | None = None,
) -> str:
    q = re.sub(r"\s+", " ", (search_query or "").lower().strip())
    for token in ("官方", "价格", "票价", "检索"):
        q = q.replace(token, " ")
    q = re.sub(r"(新疆|altay|阿勒泰|province|region)\s*", " ", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    return "|".join(
        [
            subagent,
            claim_type or "",
            lookup_phase or "",
            source_family or "",
            ticket_product or "",
            q[:80],
        ]
    )


def subagent_objective_seen(state: TravelAgentState, signature: str) -> bool:
    structured = _structured(state)
    seen = set(structured.get("s5_subagent_signatures") or [])
    return signature in seen


def record_subagent_objective(state: TravelAgentState, signature: str) -> None:
    structured = _structured(state)
    seen = list(structured.get("s5_subagent_signatures") or [])
    if signature not in seen:
        seen.append(signature)
    structured["s5_subagent_signatures"] = seen[-48:]
    state.structured_result = structured


def order_ticket_gap_tools(state: TravelAgentState, tools: list[str]) -> list[str]:
    """Search before official discovery when no harvested URLs."""
    has_urls = has_ticket_url_inputs(state)
    search_first = {"search_mcp", "keyword_search_agent"}
    official = {
        "official_source_discovery_mcp",
        "official_page_reader_mcp",
        "browser_mcp",
    }
    ordered: list[str] = []
    rest: list[str] = []
    for t in tools:
        resolved = resolve_tool_name(t)
        if resolved in search_first:
            if not has_urls:
                ordered.append(t)
            else:
                rest.append(t)
        elif resolved in official:
            if has_urls:
                ordered.append(t)
            else:
                rest.append(t)
        else:
            rest.append(t)
    if not has_urls and not any(resolve_tool_name(t) in search_first for t in ordered):
        for t in tools:
            if resolve_tool_name(t) == "search_mcp" and t not in ordered:
                ordered.insert(0, t)
    out: list[str] = []
    for t in [*ordered, *rest]:
        if t not in out:
            out.append(t)
    return out


__all__ = [
    "map_family_attempted",
    "normalize_subagent_objective",
    "official_family_attempted_or_skipped",
    "order_ticket_gap_tools",
    "platform_family_attempted",
    "record_official_discovery_skipped",
    "record_skip",
    "record_subagent_objective",
    "search_family_attempted",
    "subagent_objective_seen",
    "ticket_lookup_has_price_evidence",
    "ticket_lookup_retrieval_complete_by_family",
]
