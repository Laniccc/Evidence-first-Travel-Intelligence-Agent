"""Tiered query escalation for ticket_price hard-fact lookups."""

from __future__ import annotations

from app.orchestrator.fact_lookup_anchor_policy import resolved_place_label
from app.orchestrator.ticket_product_policy import (
    build_ticket_price_search_queries,
    ensure_ticket_product_context,
    place_aliases_for_ticket,
    ticket_product_search_queries,
)
from app.orchestrator.ticket_area_policy import is_ticket_charge_policy_query
from app.schemas.user_query import TravelAgentState

TicketQueryTier = str

_TIER_ORDER: tuple[TicketQueryTier, ...] = (
    "official",
    "charge_policy",
    "ticket_platform",
    "scenic_alias",
    "ticket_office",
    "announcement",
)


def _city_label(state: TravelAgentState) -> str:
    frame = state.semantic_frame
    if frame and frame.entities and frame.entities.city:
        return str(frame.entities.city).strip()
    return ""


def build_ticket_price_escalation_queries(
    state: TravelAgentState,
    *,
    max_queries: int = 12,
) -> list[tuple[TicketQueryTier, str]]:
    """Return (tier, query) pairs for ticket hard-fact retrieval."""
    place = resolved_place_label(state)
    if not place:
        frame = state.semantic_frame
        if frame and frame.entities and frame.entities.places:
            place = str(frame.entities.places[0]).strip()
    if not place:
        return []

    ensure_ticket_product_context(state)
    city = _city_label(state)
    by_tier: dict[TicketQueryTier, list[str]] = {tier: [] for tier in _TIER_ORDER}
    seen: set[str] = set()

    def _queue(tier: TicketQueryTier, query: str) -> None:
        q = " ".join(query.split()).strip()
        if not q or q in seen:
            return
        seen.add(q)
        by_tier[tier].append(q)

    product_queries = ticket_product_search_queries(state, place)
    if product_queries:
        for q in product_queries:
            _queue("official", q)
    else:
        for q in (
            f"{place} 官网 门票 价格",
            f"{place} 官方 票价",
            f"{place} 景区 门票 价格",
        ):
            _queue("official", q)

    if is_ticket_charge_policy_query(state):
        stems = [place]
        if city and not str(place).startswith(city):
            stems.append(f"{city}{place}")
        for stem in dict.fromkeys(stems):
            for q in (
                f"{stem} 需要门票吗 免费开放",
                f"{stem} 免费开放 内部景点 单独购票",
                f"{stem} 开放区域 免费开放 门票",
                f"{stem} 门票 免费开放 单独收费",
            ):
                _queue("charge_policy", q)

    for q in (
        f"{place} 携程 门票 价格",
        f"{place} 飞猪 票价",
        f"{place} 美团 门票",
    ):
        _queue("ticket_platform", q)

    for alias in place_aliases_for_ticket(state)[:4]:
        if alias == place:
            continue
        _queue("scenic_alias", f"{alias} 门票 价格")
        _queue("scenic_alias", f"{alias} 官方 票价")

    for stem in (place, *place_aliases_for_ticket(state)[:2]):
        _queue("ticket_office", f"{stem} 售票处 票价")
        _queue("ticket_office", f"{stem} 游客服务中心 门票")

    for q in (
        f"{place} 门票 公告",
        f"{place} 票价 调整 通知",
        f"{city}{place} 文旅局 门票 通知" if city else f"{place} 文旅局 门票 通知",
    ):
        _queue("announcement", q)

    for q in build_ticket_price_search_queries(state):
        tier = "official" if "官方" in q or "官网" in q else "scenic_alias"
        _queue(tier, q)

    out: list[tuple[TicketQueryTier, str]] = []
    picked: set[str] = set()
    for tier in _TIER_ORDER:
        for q in by_tier[tier]:
            if q not in picked:
                out.append((tier, q))
                picked.add(q)
                break
    for tier in _TIER_ORDER:
        for q in by_tier[tier]:
            if q not in picked:
                out.append((tier, q))
                picked.add(q)
    return out[:max_queries]


def escalation_queries_flat(state: TravelAgentState, *, max_queries: int = 12) -> list[str]:
    return [q for _tier, q in build_ticket_price_escalation_queries(state, max_queries=max_queries)]


def tiers_present(state: TravelAgentState, *, max_queries: int = 12) -> set[TicketQueryTier]:
    return {tier for tier, _q in build_ticket_price_escalation_queries(state, max_queries=max_queries)}
