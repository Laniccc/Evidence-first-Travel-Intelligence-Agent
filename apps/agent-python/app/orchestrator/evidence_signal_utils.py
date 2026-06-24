"""Detect multi-source value spread for S5 contradiction decomposition."""

from __future__ import annotations

import re

from app.schemas.evidence import ClaimType, Evidence
from app.schemas.user_query import TravelAgentState

_PRICE_RE = re.compile(r"(\d{2,4})\s*元")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}")


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


def multi_value_signal_for_need(state: TravelAgentState, information_need: str) -> bool:
    evidence = list(state.evidence)
    if information_need == "ticket_price":
        amounts = ticket_price_amounts(evidence)
        return len(amounts) >= 2
    if information_need == "opening_hours":
        return len(opening_hour_signatures(evidence)) >= 2
    values = _claim_type_values(evidence, information_need)
    normalized = {re.sub(r"\s+", " ", v)[:80] for v in values}
    return len(normalized) >= 2
