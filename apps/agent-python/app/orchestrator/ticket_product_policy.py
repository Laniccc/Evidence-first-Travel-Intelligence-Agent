"""Ticket product sub-types (boat/cruise, etc.) for ticket_price lookups."""

from __future__ import annotations

import re

from app.orchestrator.fact_lookup_anchor_policy import resolved_place_label
from app.schemas.user_query import TravelAgentState

_BOAT_TICKET_RE = re.compile(
    r"游船|船票|双湖游船|湖上游览|游船票|码头|快艇|游艇|cruise|boat\s*ticket",
    re.I,
)
_EXCLUDE_GENERAL_TICKET = ("景区大门票", "区间车票", "观光车票", "门票通票")
_SERVICE_POI_RE = re.compile(r"码头|游船|售票处|双湖")


def extract_ticket_product_context(query: str) -> dict | None:
    text = (query or "").strip()
    if not text or not _BOAT_TICKET_RE.search(text):
        return None
    keywords = ["游船", "船票"]
    if "双湖游船" in text:
        keywords.append("双湖游船")
    if "码头" in text:
        keywords.append("码头")
    for token in re.findall(r"[\u4e00-\u9fff]{2,10}(?:码头|景区|风景区|湖)", text):
        if token not in keywords:
            keywords.append(token)
    return {
        "ticket_product": "boat_ticket",
        "ticket_product_keywords": list(dict.fromkeys(keywords)),
        "exclude_ticket_types": list(_EXCLUDE_GENERAL_TICKET),
    }


def ensure_ticket_product_context(state: TravelAgentState) -> dict | None:
    structured = dict(state.structured_result or {})
    ctx = structured.get("ticket_product_context")
    if isinstance(ctx, dict) and ctx.get("ticket_product"):
        state.structured_result = structured
        return ctx
    ctx = extract_ticket_product_context(state.raw_user_query or "")
    if ctx:
        structured["ticket_product_context"] = ctx
        state.structured_result = structured
    return ctx


def product_keywords_for_ticket(state: TravelAgentState) -> list[str]:
    ctx = ensure_ticket_product_context(state)
    if not ctx:
        return []
    return list(ctx.get("ticket_product_keywords") or [])


def ticket_product_keywords(state: TravelAgentState) -> list[str]:
    """Backward-compatible alias — product keywords only (not place names)."""
    return product_keywords_for_ticket(state)


def place_aliases_for_ticket(state: TravelAgentState) -> list[str]:
    from app.orchestrator.ticket_lookup_helpers import build_ticket_place_aliases

    product_only = set(product_keywords_for_ticket(state)) | {"游船", "船票", "湖上游览"}
    aliases = build_ticket_place_aliases(state)
    out: list[str] = []
    for alias in aliases:
        if alias in product_only:
            continue
        if alias not in out:
            out.append(alias)
    place = resolved_place_label(state)
    for extra in (place, f"{place}景区" if place and "景区" not in place else None, f"{place}码头" if place else None):
        if extra and extra not in out and extra not in product_only:
            out.append(extra)
    return out[:10]


def ticket_product_search_queries(state: TravelAgentState, place: str) -> list[str]:
    ctx = ensure_ticket_product_context(state)
    if not ctx or not place:
        return []
    if ctx.get("ticket_product") != "boat_ticket":
        return []
    queries: list[str] = []
    stems = [place]
    if "景区" not in place:
        stems.append(f"{place}景区")
    for stem in stems:
        queries.extend(
            [
                f"{stem} 游船 船票 价格",
                f"{stem} 游船 票价",
                f"{stem} 双湖游船 船票",
                f"{stem}码头 游船票",
                f"{stem} 游船 官方 票价",
            ]
        )
    return list(dict.fromkeys(queries))[:8]


def build_ticket_price_search_queries(state: TravelAgentState) -> list[str]:
    """Entity + product aware search queries for ticket_price."""
    place = resolved_place_label(state)
    if not place:
        frame = state.semantic_frame
        if frame and frame.entities and frame.entities.places:
            place = frame.entities.places[0]
    if not place:
        return []
    boat = ticket_product_search_queries(state, place)
    if boat:
        return boat
    return list(
        dict.fromkeys(
            [
                f"{place} 门票 价格",
                f"{place} 官方 票价",
                f"{place} 官网 门票",
                f"{place} 购票 价格",
            ]
        )
    )[:6]
