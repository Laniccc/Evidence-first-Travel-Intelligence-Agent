"""Ticket-price scope audit.

Human lookup flow for ticket prices is not just "find a number":
1. identify the requested product scope,
2. classify each evidence row into entrance/add-on/bundle/transport,
3. decide which source classes can support the final answer.
"""

from __future__ import annotations

from typing import Any

from app.schemas.claim_facts import TicketPriceFact
from app.schemas.evidence import ClaimType, Evidence

TICKET_CLAIMS = {
    "ticket_price",
    "entrance_ticket_price",
    "boat_ticket_price",
    "shuttle_bus_ticket_price",
    "cable_car_ticket_price",
}

ENTRANCE_HINTS = (
    "大门票",
    "门票",
    "入园票",
    "入馆票",
    "成人票",
    "旺季",
    "淡季",
    "admission",
    "entrance",
)

ADDON_HINTS = (
    "珍宝馆",
    "钟表馆",
    "特展",
    "展览",
    "讲解",
    "导览",
    "午门",
    "神武门",
    "御花园",
    "角楼",
    "太和殿",
    "慈宁宫",
    "内馆",
)

TRANSPORT_HINTS = (
    "游船",
    "船票",
    "观光车",
    "区间车",
    "景交车",
    "索道",
    "缆车",
    "摆渡车",
)

BUNDLE_HINTS = (
    "套票",
    "联票",
    "套餐",
    "含",
    "+",
    "组合",
)

OFFICIAL_SOURCE_CLASSES = {
    "official",
    "official_page",
    "government",
    "tourism_board",
}

PLATFORM_SOURCE_CLASSES = {
    "ticket_platform",
    "platform",
}


def text_for_ticket_scope(value: Any) -> str:
    """Collect text fields that describe a ticket product."""
    if isinstance(value, TicketPriceFact):
        parts = [
            value.ticket_product,
            value.ticket_name,
            value.raw_text,
            value.source_url,
            value.booking_url,
        ]
    elif isinstance(value, dict):
        parts = [
            value.get("ticket_product"),
            value.get("ticket_name"),
            value.get("summary_line"),
            value.get("raw_text"),
            value.get("source_url"),
            value.get("booking_url"),
        ]
    else:
        parts = [value]
    return " ".join(str(p or "") for p in parts).strip()


def evidence_ticket_blob(ev: Evidence) -> str:
    parts = [ev.source_name, ev.source_url, ev.place_name]
    for claim in ev.claims or []:
        parts.extend([claim.value, claim.raw_text, claim.normalized_value])
    return " ".join(str(p or "") for p in parts).strip()


def requested_ticket_product(claim_type: str | None) -> str:
    if claim_type == "boat_ticket_price":
        return "boat_ticket"
    if claim_type == "shuttle_bus_ticket_price":
        return "shuttle_bus"
    if claim_type == "cable_car_ticket_price":
        return "cable_car"
    return "entrance_ticket"


def classify_ticket_scope(text: str, *, claim_type: str | None = None) -> str:
    blob = str(text or "")
    requested = requested_ticket_product(claim_type)
    has_transport = any(h in blob for h in TRANSPORT_HINTS)
    has_addon = any(h in blob for h in ADDON_HINTS)
    has_bundle = any(h in blob for h in BUNDLE_HINTS)
    has_entrance = any(h in blob for h in ENTRANCE_HINTS)

    if requested == "boat_ticket":
        return "requested_product" if "游船" in blob or "船票" in blob else "other_product"
    if requested == "shuttle_bus":
        return "requested_product" if any(h in blob for h in ("观光车", "区间车", "景交车")) else "other_product"
    if requested == "cable_car":
        return "requested_product" if any(h in blob for h in ("索道", "缆车")) else "other_product"

    if has_transport:
        return "transport_or_service"
    if has_addon:
        return "addon_or_internal"
    if has_bundle:
        return "combo_or_bundle"
    if has_entrance:
        return "entrance_ticket"
    return "unknown"


def is_main_ticket_scope(text: str, *, claim_type: str | None = None) -> bool:
    scope = classify_ticket_scope(text, claim_type=claim_type)
    if requested_ticket_product(claim_type) == "entrance_ticket":
        return scope in {"entrance_ticket", "unknown"}
    return scope == "requested_product"


def is_platform_addon_for_claim(text: str, *, claim_type: str | None = None) -> bool:
    return not is_main_ticket_scope(text, claim_type=claim_type)


def source_class_can_finalize(source_class: str, strength: str) -> bool:
    src = str(source_class or "").lower()
    level = str(strength or "").lower()
    return src in OFFICIAL_SOURCE_CLASSES and level in {"strong", "partial"}


def fact_can_support_claim(fact: TicketPriceFact | dict, *, claim_type: str | None = None) -> bool:
    text = text_for_ticket_scope(fact)
    source_class = (
        fact.source_class if isinstance(fact, TicketPriceFact) else str(fact.get("source_class") or "")
    )
    if str(source_class).lower() in PLATFORM_SOURCE_CLASSES and is_platform_addon_for_claim(
        text, claim_type=claim_type
    ):
        return False
    return is_main_ticket_scope(text, claim_type=claim_type)


def rank_ticket_fact(row: dict, *, claim_type: str | None = None) -> tuple[int, int, int, float]:
    source_class = str(row.get("source_class") or "").lower()
    strength = str(row.get("evidence_strength") or "").lower()
    scope = classify_ticket_scope(text_for_ticket_scope(row), claim_type=claim_type)
    price = row.get("adult_price")
    has_positive_price = isinstance(price, int | float) and price > 0

    if source_class in OFFICIAL_SOURCE_CLASSES:
        source_rank = 0
    elif source_class in PLATFORM_SOURCE_CLASSES:
        source_rank = 2
    elif source_class in {"web", "search_snippet"}:
        source_rank = 3
    else:
        source_rank = 4
    scope_rank = {
        "entrance_ticket": 0,
        "requested_product": 0,
        "combo_or_bundle": 2,
        "unknown": 3,
        "addon_or_internal": 5,
        "transport_or_service": 5,
        "other_product": 6,
    }.get(scope, 4)
    strength_rank = {"strong": 0, "partial": 1, "candidate_only": 2, "weak": 3}.get(strength, 3)
    return (scope_rank, source_rank, strength_rank, 0 if has_positive_price else 1)


def preferred_ticket_facts(facts: list[TicketPriceFact], *, claim_type: str | None = None) -> list[TicketPriceFact]:
    rows = [f for f in facts if fact_can_support_claim(f, claim_type=claim_type)]
    return sorted(
        rows,
        key=lambda f: rank_ticket_fact({**f.model_dump(), "summary_line": f.summary_line()}, claim_type=claim_type),
    )


def evidence_has_main_ticket_scope(ev: Evidence, *, claim_type: str | None = None) -> bool:
    return is_main_ticket_scope(evidence_ticket_blob(ev), claim_type=claim_type)
