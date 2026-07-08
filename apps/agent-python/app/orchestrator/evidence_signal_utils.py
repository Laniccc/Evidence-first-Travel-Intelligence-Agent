"""Detect multi-source value spread for S5 contradiction decomposition."""

from __future__ import annotations

import re

from app.schemas.evidence import ClaimType, Evidence
from app.schemas.user_query import TravelAgentState

_PRICE_RE = re.compile(r"(\d{2,4})\s*元")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}")
_KM_RE = re.compile(r"(\d{2,4})\s*(?:公里|km|KM)", re.I)
_DAY_TRIP_RE = re.compile(r"(一天|一日游|当日|够玩)", re.I)

_VISIT_DURATION_CLAIM_TYPES = (
    ClaimType.TRAVEL_ADVICE.value,
    "walking_intensity",
    "general_travel_advice",
    "visit_duration",
    "itinerary_feasibility",
)
_DISTANCE_CLAIM_TYPES = (
    ClaimType.TRAVEL_ADVICE.value,
    ClaimType.TRANSIT.value,
    "distance",
    "duration",
    "route_plan",
    "transport_planning",
    "itinerary_feasibility",
)


def _claim_type_values(evidence: list, claim_type: str) -> list[str]:
    values: list[str] = []
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct == claim_type or claim_type in ct:
                text = str(claim.value or "").strip()
                if text and len(text) >= 4:
                    values.append(text)
    return values


def _values_for_claim_types(evidence: list, claim_types: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for claim_type in claim_types:
        values.extend(_claim_type_values(evidence, claim_type))
    return values


def ticket_price_amounts(evidence: list) -> set[int]:
    amounts: set[int] = set()
    for text in _claim_type_values(evidence, ClaimType.TICKET_PRICE.value):
        for match in _PRICE_RE.finditer(text):
            amounts.add(int(match.group(1)))
    return amounts


def opening_hour_signatures(evidence: list) -> set[str]:
    sigs: set[str] = set()
    for text in _claim_type_values(evidence, ClaimType.OPENING_HOURS.value):
        times = sorted(set(_TIME_RE.findall(text)))
        if times:
            sigs.add("|".join(times[:6]))
    return sigs


def visit_duration_buckets(evidence: list) -> set[str]:
    buckets: set[str] = set()
    for text in _values_for_claim_types(evidence, _VISIT_DURATION_CLAIM_TYPES):
        if re.search(r"\d+\s*天|两日|三日|2-3天|2天|3天", text):
            buckets.add("multi_day")
        if re.search(r"\d+\s*小时|4-5小时|半日", text):
            buckets.add("hours")
        if _DAY_TRIP_RE.search(text):
            buckets.add("one_day")
    return buckets


def distance_km_values(evidence: list) -> set[int]:
    kms: set[int] = set()
    for text in _values_for_claim_types(evidence, _DISTANCE_CLAIM_TYPES):
        for match in _KM_RE.finditer(text):
            kms.add(int(match.group(1)))
    return kms


def distance_values_conflict(evidence: list) -> bool:
    kms = distance_km_values(evidence)
    if len(kms) < 2:
        return False
    lo, hi = min(kms), max(kms)
    return (hi - lo) / max(lo, 1) > 0.25


def multi_value_signal_for_need(state: TravelAgentState, information_need: str) -> bool:
    evidence = list(state.evidence)
    if information_need == "ticket_price":
        return len(ticket_price_amounts(evidence)) >= 2
    if information_need == "opening_hours":
        return len(opening_hour_signatures(evidence)) >= 2
    if information_need in {"visit_duration", "walking_intensity", "itinerary_feasibility"}:
        return len(visit_duration_buckets(evidence)) >= 2
    if information_need in {"distance", "duration", "route_plan", "transport_planning", "transit"}:
        return distance_values_conflict(evidence)
    values = _claim_type_values(evidence, information_need)
    normalized = {re.sub(r"\s+", " ", v)[:80] for v in values}
    return len(normalized) >= 2


def contradiction_needs_for_state(state: TravelAgentState) -> list[str]:
    """Ordered claim/need types to check for multi-source contradictions."""
    ordered: list[str] = []
    residual = state.user_need_residual
    if residual:
        for claim in residual.claim_requirements:
            if claim.claim_type and claim.claim_type not in ordered:
                ordered.append(claim.claim_type)
        for need in residual.information_needs:
            if need.need_type and need.need_type not in ordered:
                ordered.append(need.need_type)
    contract = state.response_contract
    if contract:
        for claim in contract.claim_requirements:
            if claim.claim_type not in ordered:
                ordered.append(claim.claim_type)
    frame = state.semantic_frame
    if frame and frame.information_needs:
        for need in frame.information_needs:
            if need not in ordered:
                ordered.append(need)

    for synthetic in ("visit_duration", "distance"):
        if synthetic not in ordered:
            ordered.append(synthetic)
    return ordered


def any_contradiction_signal(state: TravelAgentState) -> tuple[str, bool]:
    """Return first need type with a contradiction signal, if any."""
    structured = state.structured_result or {}
    decomposed = set(structured.get("_decomposed_needs") or [])
    for need in contradiction_needs_for_state(state):
        if need in decomposed:
            continue
        if multi_value_signal_for_need(state, need):
            return need, True
    return "", False


def is_day_trip_query(frame) -> bool:
    if frame is None:
        return False
    text = f"{getattr(frame, 'raw_query', '')} {getattr(frame, 'normalized_request', '')}"
    return bool(_DAY_TRIP_RE.search(text))
