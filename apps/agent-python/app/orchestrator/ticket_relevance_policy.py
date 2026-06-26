"""Ticket-price / boat-ticket relevance and search-noise filtering."""

from __future__ import annotations

import re

from app.orchestrator.fact_lookup_anchor_policy import resolved_place_label
from app.orchestrator.fact_lookup_policy import primary_fact_need_from_state
from app.schemas.user_query import TravelAgentState

_TICKET_NOISE_RE = re.compile(
    r"世界杯|楚超|联赛|演唱会|音乐节|足球|篮球|体育赛事|"
    r"住宿预算|酒店预算|机票|火车票|高铁票|"
    r"软件下载|官方下载|APP下载|"
    r"鄂州|北京住宿|上海住宿|广州住宿",
    re.I,
)
_PRICE_SIGNAL_RE = re.compile(
    r"价格|票价|门票|元|¥|rmb|成人票|优惠票|购票|船票|游船",
    re.I,
)
_BOAT_SIGNAL_RE = re.compile(r"游船|船票|双湖游船|码头|快艇|游艇|湖上", re.I)
_TRUNCATED_URL_RE = re.compile(r"\.\.\.|…|\d+天前", re.I)


def place_anchor_terms(state: TravelAgentState) -> list[str]:
    terms: list[str] = []
    place = resolved_place_label(state)
    if place:
        terms.append(place)
    frame = state.semantic_frame
    if frame and frame.entities:
        for p in frame.entities.places or []:
            if p and p not in terms:
                terms.append(p.strip())
        if frame.entities.city and frame.entities.city not in terms:
            terms.append(frame.entities.city.strip())
    raw = state.raw_user_query or ""
    for token in re.findall(r"[\u4e00-\u9fff]{2,12}", raw):
        if token not in terms and len(token) >= 2:
            if any(x in token for x in ("喀纳斯", "景区", "码头", "游船", "湖")):
                terms.append(token)
    if place and "景区" not in place:
        terms.append(f"{place}景区")
    return [t for t in terms if t][:8]


def is_ticket_search_noise(text: str) -> bool:
    blob = (text or "").strip()
    if not blob:
        return True
    if _TICKET_NOISE_RE.search(blob):
        return True
    return False


def is_noise_discovery_url(url: str) -> bool:
    u = (url or "").strip()
    if not u:
        return True
    if _TRUNCATED_URL_RE.search(u):
        return True
    if "..." in u or "…" in u:
        return True
    return False


def _matches_place(blob: str, anchors: list[str]) -> bool:
    if not anchors:
        return True
    for a in anchors:
        if not a:
            continue
        if a in blob:
            return True
        if len(a) >= 4:
            for n in (3, 4):
                for i in range(len(a) - n + 1):
                    if a[i : i + n] in blob:
                        return True
    return False


def passes_boat_ticket_relevance(blob: str, anchors: list[str]) -> bool:
    if is_ticket_search_noise(blob):
        return False
    if not _matches_place(blob, anchors):
        return False
    if not _BOAT_SIGNAL_RE.search(blob):
        return False
    if not _PRICE_SIGNAL_RE.search(blob):
        return False
    return True


def passes_ticket_price_relevance(blob: str, anchors: list[str], *, boat_only: bool = False) -> bool:
    if is_ticket_search_noise(blob):
        return False
    if not _matches_place(blob, anchors):
        return False
    if boat_only:
        return passes_boat_ticket_relevance(blob, anchors)
    if not _PRICE_SIGNAL_RE.search(blob):
        return False
    return True


def ticket_relevance_score(
    state: TravelAgentState,
    claim_type: str,
    value: str,
    *,
    source_name: str = "",
    source_url: str = "",
) -> float:
    need = primary_fact_need_from_state(state)
    if need != "ticket_price" and claim_type not in {
        "ticket_price",
        "ticket_price_candidate",
        "price_candidate",
        "general_fact",
        "travel_advice",
    }:
        return 0.55
    from app.orchestrator.ticket_product_policy import ensure_ticket_product_context

    ctx = ensure_ticket_product_context(state)
    boat_only = bool(ctx and ctx.get("ticket_product") == "boat_ticket")
    blob = f"{value} {source_name} {source_url}"
    anchors = place_anchor_terms(state)
    if boat_only:
        return 0.9 if passes_boat_ticket_relevance(blob, anchors) else 0.0
    if claim_type in {"ticket_price", "ticket_price_candidate", "price_candidate"}:
        return 0.85 if passes_ticket_price_relevance(blob, anchors) else 0.0
    if claim_type in {"general_fact", "travel_advice"} and need == "ticket_price":
        return 0.75 if passes_ticket_price_relevance(blob, anchors, boat_only=False) else 0.0
    return 0.35


def discovery_hit_relevant(
    hit: dict,
    *,
    place_name: str,
    claim_type: str | None,
    anchor_terms: list[str] | None = None,
    ticket_product: str | None = None,
) -> bool:
    url = str(hit.get("url") or "").strip()
    if url and is_noise_discovery_url(url):
        return False
    title = str(hit.get("title") or "")
    snippet = str(hit.get("snippet") or "")
    blob = f"{title} {snippet} {url}"
    anchors = list(anchor_terms or [])
    if place_name and place_name not in anchors:
        anchors.insert(0, place_name)
    if claim_type == "ticket_price":
        if ticket_product == "boat_ticket":
            if passes_boat_ticket_relevance(blob, anchors):
                return True
            return _matches_place(blob, anchors) and bool(url)
        if passes_ticket_price_relevance(blob, anchors):
            return True
        return _matches_place(blob, anchors) and bool(url)
    return _matches_place(blob, anchors) or not anchors
