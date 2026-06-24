"""Follow official-site subpages until structured hard-fact fields are found."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from app.schemas.evidence import Claim, ClaimType
from tools.mcp.adapters.page_content_extractor import claim_substantively_satisfies_need
from tools.official_source.url_normalizer import extract_domain, is_fetchable_url
from tools.official_source.whitelist_resolver import resolve_official_whitelist_url

_NEED_TO_CLAIM = {
    "opening_hours": ClaimType.OPENING_HOURS,
    "ticket_price": ClaimType.TICKET_PRICE,
    "reservation_policy": ClaimType.RESERVATION,
    "temporary_closure": ClaimType.TRAVEL_ADVICE,
}

_SUBPAGE_ANCHOR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "opening_hours": (
        "参观须知",
        "开放时间",
        "开馆",
        "营业时间",
        "visit",
        "hours",
        "opening",
    ),
    "ticket_price": ("门票", "票价", "票务", "ticket", "price", "参观须知"),
    "reservation_policy": ("预约", "预订", "购票", "reservation", "booking", "参观须知"),
    "temporary_closure": ("公告", "闭园", "通知", "notice", "closure"),
}

# Known detail pages when homepage nav is JS-heavy (e.g. dpm.org.cn).
_OFFICIAL_SITE_DETAIL_PATHS: dict[str, dict[str, list[str]]] = {
    "dpm.org.cn": {
        "opening_hours": ["https://www.dpm.org.cn/Visit.html"],
        "ticket_price": ["https://www.dpm.org.cn/Visit.html"],
        "reservation_policy": ["https://www.dpm.org.cn/Visit.html"],
        "temporary_closure": ["https://www.dpm.org.cn/Visit.html"],
    },
}

_HREF_RE = re.compile(r"""href=["']([^"'#]+)["']""", re.I)
_ANCHOR_TEXT_RE = re.compile(r">([^<]{2,40})<", re.I)


def target_claim_type(information_need: str | None) -> ClaimType | None:
    if not information_need:
        return None
    try:
        return ClaimType(information_need)
    except ValueError:
        return _NEED_TO_CLAIM.get(information_need)


def claims_satisfy_need(claims: list[Claim], information_need: str | None) -> bool:
    if not information_need:
        return bool(claims)
    return any(claim_substantively_satisfies_need(claim, information_need) for claim in claims)


def extract_links_from_html(html: str, base_url: str) -> list[tuple[str, str]]:
    if not html:
        return []
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(html):
        href = href.strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        full = urljoin(base_url, href)
        if not is_fetchable_url(full):
            continue
        if extract_domain(full) != extract_domain(base_url):
            continue
        if full in seen:
            continue
        seen.add(full)
        links.append((full, ""))
    return links


def _keyword_links(html: str, base_url: str, keywords: tuple[str, ...]) -> list[str]:
    ranked: list[str] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(html or ""):
        full = urljoin(base_url, href.strip())
        if not is_fetchable_url(full) or full in seen:
            continue
        if extract_domain(full) != extract_domain(base_url):
            continue
        seen.add(full)
        tail = f"{full} {(html or '')[max(0, (html or '').find(href)-60):(html or '').find(href)+60]}"
        if any(kw.lower() in tail.lower() or kw in tail for kw in keywords):
            ranked.append(full)
    return ranked


def known_detail_urls(base_url: str, information_need: str | None) -> list[str]:
    domain = extract_domain(base_url)
    by_need = _OFFICIAL_SITE_DETAIL_PATHS.get(domain, {})
    if information_need and information_need in by_need:
        return list(by_need[information_need])
    if information_need:
        return list(by_need.get("opening_hours", []))
    return []


def plan_follow_urls(
    base_url: str,
    *,
    information_need: str | None,
    page_html: str | None = None,
    place_name: str | None = None,
    max_urls: int = 4,
) -> list[str]:
    """Return ordered follow-up URLs (excluding base_url)."""
    out: list[str] = []
    seen: set[str] = {base_url.rstrip("/")}

    for url in known_detail_urls(base_url, information_need):
        key = url.rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(url)

    wl = resolve_official_whitelist_url(place_name)
    if wl and wl.rstrip("/") != base_url.rstrip("/"):
        for url in known_detail_urls(wl, information_need):
            key = url.rstrip("/")
            if key not in seen:
                seen.add(key)
                out.append(url)

    keywords = _SUBPAGE_ANCHOR_KEYWORDS.get(information_need or "", ("参观须知", "官网"))
    if page_html:
        for url in _keyword_links(page_html, base_url, keywords):
            key = url.rstrip("/")
            if key not in seen:
                seen.add(key)
                out.append(url)

    return out[:max_urls]
