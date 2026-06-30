"""Track S5 retrieval attempts by source family (not claim coverage)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.orchestrator.fact_lookup_policy import primary_fact_need_from_state
from app.schemas.user_query import TravelAgentState
from app.tools.tool_name_resolver import resolve_tool_name
from tools.ticketing.provider_config import is_ticket_provider_tool, provider_configured_for_tool

_SEARCH_SUBAGENTS = frozenset({"fact_search_agent", "keyword_search_agent", "fact_lookup_agent"})
_GEO_SUBAGENTS = frozenset({"entity_resolution_agent"})
_GEO_TOOLS = frozenset(
    {
        "baidu_place_search_mcp",
        "baidu_geocode_mcp",
        "baidu_reverse_geocode_mcp",
        "entity_resolution_agent",
        "osm_mcp",
        "places_mcp",
        "wikidata_mcp",
        "wikipedia_mcp",
    }
)
_SEARCH_TOOLS = frozenset({"search_mcp", "keyword_search_agent"})
_OFFICIAL_SOURCE_TOOLS = frozenset({"official_source_discovery_mcp", "official"})
_OFFICIAL_PAGE_TOOLS = frozenset({"official_page_reader_mcp", "browser_mcp"})
_PLATFORM_TOOLS = frozenset(
    {
        "fliggy_ticket_api_mcp",
        "fliggy_ticket_snapshot_crawler_mcp",
        "ticketlens_experience_mcp",
        "ctrip_ticket_signal_crawler_mcp",
        "dianping_ticket_signal_crawler_mcp",
        "ticket_price_history_query",
        "ticket_snapshot_store",
    }
)
_MAP_TOOLS = frozenset({"baidu_place_detail_mcp", "baidu_place_search_mcp"})

_RETRIEVAL_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "ticket_price": {
        "required": ("geo_resolution", "search", "map_candidate"),
        "one_of": (
            ("official_source",),
            ("ticket_platform",),
        ),
        "optional_skip": ("official_source", "ticket_platform"),
    },
    "boat_ticket_price": {
        "required": ("geo_resolution", "search", "map_candidate"),
        "one_of": (
            ("official_source",),
            ("ticket_platform",),
        ),
        "optional_skip": ("official_source", "ticket_platform"),
    },
    "entrance_ticket_price": {
        "required": ("geo_resolution", "search", "map_candidate"),
        "one_of": (
            ("official_source",),
            ("ticket_platform",),
        ),
        "optional_skip": ("official_source", "ticket_platform"),
    },
    "opening_hours": {
        "required": ("geo_resolution", "search", "map_candidate"),
        "one_of": (("official_source", "official_page_reader"),),
        "optional_skip": ("official_source", "official_page_reader"),
    },
}


class RetrievalAttemptLedger(BaseModel):
    claim_type: str = ""
    claim_id: str | None = None
    attempted_source_families: list[str] = Field(default_factory=list)
    attempted_phases: list[str] = Field(default_factory=list)
    skipped_with_reason: dict[str, str] = Field(default_factory=dict)
    evidence_count_by_family: dict[str, int] = Field(default_factory=dict)
    hard_failures: list[str] = Field(default_factory=list)

    def families_attempted(self) -> set[str]:
        out = set(self.attempted_source_families)
        out.update(self.skipped_with_reason.keys())
        return out

    def record_family(
        self,
        family: str,
        *,
        phase: str | None = None,
        evidence_count: int = 0,
    ) -> None:
        if family and family not in self.attempted_source_families:
            self.attempted_source_families.append(family)
        if phase and phase not in self.attempted_phases:
            self.attempted_phases.append(phase)
        if evidence_count:
            self.evidence_count_by_family[family] = (
                self.evidence_count_by_family.get(family, 0) + evidence_count
            )

    def record_skip(self, family: str, reason: str) -> None:
        self.skipped_with_reason[family] = reason[:240]

    def record_failure(self, message: str) -> None:
        text = message[:240]
        if text and text not in self.hard_failures:
            self.hard_failures.append(text)

    def retrieval_complete(self) -> bool:
        spec = _RETRIEVAL_REQUIREMENTS.get(self.claim_type)
        if not spec:
            return bool(self.attempted_source_families or self.skipped_with_reason)
        families = self.families_attempted()
        for req in spec.get("required", ()):
            if req not in families:
                return False
        for group in spec.get("one_of", ()):
            if not any(f in families for f in group):
                return False
        return True

    def missing_families(self) -> list[str]:
        spec = _RETRIEVAL_REQUIREMENTS.get(self.claim_type, {})
        families = self.families_attempted()
        missing: list[str] = []
        for req in spec.get("required", ()):
            if req not in families:
                missing.append(req)
        for group in spec.get("one_of", ()):
            if not any(f in families for f in group):
                missing.append("|".join(group))
        return missing

    def to_finish_payload(self) -> dict[str, Any]:
        return {
            "retrieval_complete": self.retrieval_complete(),
            "evidence_gap_acknowledged": self.retrieval_complete(),
            "attempted_source_families": list(self.attempted_source_families),
            "skipped_with_reason": dict(self.skipped_with_reason),
            "missing": self.missing_families(),
            "hard_failures": list(self.hard_failures),
        }


def source_family_for_tool(tool_name: str) -> str | None:
    resolved = resolve_tool_name(tool_name)
    if resolved in _SEARCH_TOOLS:
        return "search"
    if resolved in _OFFICIAL_SOURCE_TOOLS:
        return "official_source"
    if resolved in _OFFICIAL_PAGE_TOOLS:
        return "official_page_reader"
    if resolved in _PLATFORM_TOOLS or is_ticket_provider_tool(resolved):
        return "ticket_platform"
    if resolved in _GEO_TOOLS or resolved.endswith("_agent") and "entity" in resolved:
        return "geo_resolution"
    if resolved in _MAP_TOOLS:
        return "map_candidate"
    if resolved == "entity_resolution_agent":
        return "geo_resolution"
    return None


def source_family_for_subagent(subagent: str) -> str | None:
    name = str(subagent or "")
    if name in _SEARCH_SUBAGENTS:
        return "search"
    if name in _GEO_SUBAGENTS:
        return "geo_resolution"
    return None


def _structured(state: TravelAgentState) -> dict:
    return dict(state.structured_result or {})


def _ledger_key(claim_type: str) -> str:
    return claim_type or "general"


def get_ledger(state: TravelAgentState, claim_type: str | None = None) -> RetrievalAttemptLedger:
    claim = claim_type or primary_fact_need_from_state(state) or "general_fact"
    structured = _structured(state)
    raw = structured.get("retrieval_ledger") or {}
    if isinstance(raw, dict) and claim in raw:
        data = raw[claim]
        if isinstance(data, dict):
            payload = dict(data)
            payload.pop("claim_type", None)
            ledger = RetrievalAttemptLedger(claim_type=claim, **payload)
            _hydrate_from_state(ledger, state)
            return ledger
    legacy = structured.get("ticket_lookup_attempts")
    ledger = RetrievalAttemptLedger(claim_type=claim)
    if isinstance(legacy, dict) and claim == "ticket_price":
        if legacy.get("official_skipped"):
            ledger.record_skip("official_source", legacy.get("official_skip_reason") or "skipped")
    _hydrate_from_state(ledger, state)
    return ledger


def save_ledger(state: TravelAgentState, ledger: RetrievalAttemptLedger) -> None:
    structured = _structured(state)
    store = structured.get("retrieval_ledger")
    if not isinstance(store, dict):
        store = {}
    store[ledger.claim_type] = ledger.model_dump()
    structured["retrieval_ledger"] = store
    if ledger.claim_type == "ticket_price" and "official_source" in ledger.skipped_with_reason:
        structured["ticket_lookup_attempts"] = {
            "official_skipped": True,
            "official_skip_reason": ledger.skipped_with_reason["official_source"],
        }
    state.structured_result = structured


def _hydrate_from_state(ledger: RetrievalAttemptLedger, state: TravelAgentState) -> None:
    for trace in state.tool_traces or []:
        family = source_family_for_tool(str(trace.tool_name or ""))
        if family:
            count = len(trace.evidence_ids or [])
            ledger.record_family(family, evidence_count=count)
    structured = _structured(state)
    if structured.get("keyword_search_results"):
        ledger.record_family("search")
    for row in structured.get("subagent_results") or []:
        sub = row.get("subagent")
        family = source_family_for_subagent(str(sub or ""))
        if family:
            ledger.record_family(family, evidence_count=int(row.get("evidence_count") or 0))
        tool = resolve_tool_name(str(row.get("selected_tool") or ""))
        tf = source_family_for_tool(tool)
        if tf:
            ledger.record_family(tf, evidence_count=int(row.get("evidence_count") or 0))
    for ev in state.evidence or []:
        src = str(getattr(ev, "source_name", "") or "").lower()
        if "websearch" in src or src in {"open-websearch", "search_mcp"}:
            ledger.record_family("search", evidence_count=1)


def record_tool_attempt(
    state: TravelAgentState,
    *,
    tool_name: str,
    claim_type: str | None = None,
    phase: str | None = None,
    evidence_count: int = 0,
    error: str | None = None,
) -> None:
    ledger = get_ledger(state, claim_type)
    family = source_family_for_tool(tool_name)
    if family:
        ledger.record_family(family, phase=phase, evidence_count=evidence_count)
    if error:
        ledger.record_failure(f"{tool_name}: {error}")
    save_ledger(state, ledger)


def record_skip(
    state: TravelAgentState,
    family: str,
    reason: str,
    *,
    claim_type: str | None = None,
) -> None:
    ledger = get_ledger(state, claim_type)
    ledger.record_skip(family, reason)
    save_ledger(state, ledger)


def record_official_discovery_skipped(state: TravelAgentState, reason: str) -> None:
    record_skip(state, "official_source", reason, claim_type="ticket_price")


def record_official_page_reader_skipped(state: TravelAgentState, reason: str, *, claim_type: str | None = None) -> None:
    record_skip(state, "official_page_reader", reason, claim_type=claim_type)


def retrieval_complete(state: TravelAgentState, claim_type: str | None = None) -> bool:
    ledger = get_ledger(state, claim_type)
    _hydrate_from_state(ledger, state)
    if ledger.claim_type == "ticket_price":
        from app.config import get_settings

        settings = get_settings()
        configured = [t for t in _PLATFORM_TOOLS if provider_configured_for_tool(t, settings)]
        families = ledger.families_attempted()
        if configured and "ticket_platform" not in families:
            return False
    return ledger.retrieval_complete()


def sync_ledger_to_state(state: TravelAgentState, claim_type: str | None = None) -> dict[str, Any]:
    ledger = get_ledger(state, claim_type)
    _hydrate_from_state(ledger, state)
    save_ledger(state, ledger)
    return ledger.to_finish_payload()
