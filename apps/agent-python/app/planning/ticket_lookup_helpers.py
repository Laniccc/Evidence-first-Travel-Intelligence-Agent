"""Ticket lookup helpers — URL harvest, aliases, source relevance."""

from __future__ import annotations

import re
from typing import Any

from app.evidence.evidence_model import Evidence, SourceType
from tools.official_source.url_normalizer import clean_search_hits_for_official_chain, hits_from_evidence_list
from tools.ticket_price_text import has_explicit_ticket_price_signal

TravelAgentState = Any

_TICKET_NOISE_DOMAINS = frozenset(
    {
        "zhihu.com",
        "sohu.com",
        "baike.baidu.com",
        "wikipedia.org",
        "zh.wikipedia.org",
    }
)
_GOV_HOME_TICKET_NOISE = re.compile(
    r"首页|政府门户|人民政府|政务公开|网站地图|领导信息",
    re.I,
)
_TICKET_PRICE_SIGNAL = re.compile(
    r"门票|票价|购票|预约|参观服务|成人票|儿童票|全价|半价|元/?人|¥|rmb",
    re.I,
)
_MUSEUM_NAME = re.compile(
    r"[\u4e00-\u9fff]{2,20}(?:博物馆|博物院|纪念馆|遗址博物馆|陵博物院)",
)
_SCENIC_SUFFIXES = ("风景名胜区", "风景区")


def _place_is_museum_entity(*names: str) -> bool:
    blob = " ".join(n for n in names if n)
    return bool(re.search(r"博物馆|博物院|纪念馆", blob))


def collect_ticket_search_hits(state: TravelAgentState) -> list[dict]:
    """Harvest search hits / URLs from accumulated evidence for official discovery."""
    hits = hits_from_evidence_list(list(state.evidence or []))
    structured = state.structured_result or {}
    for row in structured.get("keyword_search_results") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("link") or "").strip()
        if url.startswith("http"):
            hits.append(
                {
                    "url": url,
                    "title": row.get("title"),
                    "snippet": row.get("snippet") or row.get("description"),
                }
            )
    seen: set[str] = set()
    deduped: list[dict] = []
    for hit in hits:
        url = str(hit.get("url") or "").strip()
        key = url or str(hit.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return clean_search_hits_for_official_chain(deduped)


def collect_official_discovery_search_results(
    state: TravelAgentState,
) -> tuple[list[dict], list[str]]:
    """Single source for official_source_discovery_mcp search_results + urls."""
    hits = collect_ticket_search_hits(state)
    urls: list[str] = []
    for hit in hits:
        url = str(hit.get("url") or "").strip()
        if url.startswith("http") and url not in urls:
            urls.append(url)
    return hits, urls


def collect_ticket_search_urls(state: TravelAgentState) -> list[str]:
    urls: list[str] = []
    for hit in collect_ticket_search_hits(state):
        url = str(hit.get("url") or "").strip()
        if url.startswith("http") and url not in urls:
            urls.append(url)
    return urls


def has_ticket_url_inputs(state: TravelAgentState) -> bool:
    return bool(collect_ticket_search_urls(state))


def build_ticket_place_aliases(state: TravelAgentState) -> list[str]:
    """Build scenic/ticket aliases from anchor — no fake museum suffixes."""
    names: list[str] = []
    frame = state.semantic_frame
    if frame and frame.entities and frame.entities.places:
        names.extend(p.strip() for p in frame.entities.places if p and p.strip())
    structured = state.structured_result or {}
    anchor = structured.get("fact_anchor") or {}
    anchor_names = [
        str(anchor.get(key) or "").strip()
        for key in ("resolved_name", "canonical_name", "display_name")
    ]
    for val in anchor_names:
        if val and val not in names:
            names.append(val)
    for alias in anchor.get("aliases") or []:
        text = str(alias).strip()
        if text and text not in names:
            names.append(text)
    city = (frame.entities.city if frame and frame.entities else None) or ""
    is_museum = _place_is_museum_entity(*(names + anchor_names))
    if is_museum:
        for ev in state.evidence or []:
            if not isinstance(ev, Evidence):
                continue
            for claim in ev.claims or []:
                blob = f"{getattr(claim, 'value', '')} {getattr(claim, 'raw_text', '')}"
                for m in _MUSEUM_NAME.finditer(blob):
                    token = m.group(0).strip()
                    if token and token not in names:
                        names.append(token)
    bases = list(names)
    for base in bases:
        if not base:
            continue
        if city:
            combo = f"{city}{base}"
            if combo not in names:
                names.append(combo)
            if city not in base:
                spaced = f"{city} {base}"
                if spaced not in names:
                    names.append(spaced)
        if not is_museum:
            for suffix in _SCENIC_SUFFIXES:
                if suffix not in base:
                    variant = f"{base}{suffix}"
                    if variant not in names:
                        names.append(variant)
    return names[:10]


def is_official_background_only_for_ticket(ev: Evidence) -> bool:
    import importlib

    judgement = importlib.import_module("app.evidence.official_source_judgement")
    cand = judgement.parse_candidate_from_evidence(ev)
    if not cand:
        return False
    if cand.has_ticket_info:
        return False
    if "destination_background" in (cand.supports_claim_types or []):
        return True
    result = judgement.judge_candidate_for_claim(cand, "ticket_price")
    return result.coverage_tier == "weak" and "background" in (result.reason or "")


def is_ticket_price_noise_evidence(ev: Evidence, *, claim_type: str = "ticket_price") -> bool:
    if claim_type != "ticket_price":
        return False
    if is_official_background_only_for_ticket(ev):
        return True
    source = (ev.source_name or "").lower()
    url = (ev.source_url or "").lower()
    domain = url.split("/")[2] if "://" in url else ""
    if any(d in domain or d in url for d in _TICKET_NOISE_DOMAINS):
        return True
    if domain.endswith(".gov.cn") or ".gov.cn" in url:
        blob = " ".join(
            f"{getattr(c, 'value', '')} {getattr(c, 'raw_text', '')}"
            for c in (ev.claims or [])
        )
        if _GOV_HOME_TICKET_NOISE.search(blob) and not _TICKET_PRICE_SIGNAL.search(blob):
            return True
    if ev.source_type == SourceType.MODEL_PRIOR:
        return True
    return False


def ticket_platform_candidate_quality(ev: Evidence) -> str:
    """Return coverage tier hint for platform ticket evidence."""
    source = (ev.source_name or "").lower()
    if any(x in source for x in ("fliggy", "飞猪", "ctrip", "携程", "ticketlens", "dianping", "点评")):
        for claim in ev.claims or []:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct in {"ticket_price_candidate", "price_candidate", "ticket_price"}:
                text = f"{claim.value or ''} {claim.raw_text or ''}"
                if re.search(r"\d+", text):
                    return "partial"
        return "weak"
    if "baidu" in source:
        return "partial"
    return "weak"


def build_ticket_product_detail_retry(
    evidence: list,
    *,
    claim_type: str = "ticket_price",
) -> dict | None:
    """Build a targeted retry when a platform product is structured but has no price."""
    product_candidates: list[str] = []
    detail_urls: list[str] = []
    price_found = False
    price_claim_types = {
        "ticket_price",
        "ticket_price_candidate",
        "price_candidate",
        "activity_price",
    }
    product_claim_types = {"activity_price", "ticket_type"}

    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        evidence_has_product = False
        for claim in ev.claims or []:
            ctype = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            value = str(claim.value or "").strip()
            raw_text = str(claim.raw_text or "").strip()
            price_blob = " ".join(part for part in (value, raw_text) if part)
            if ctype in price_claim_types and has_explicit_ticket_price_signal(price_blob):
                price_found = True
            if ctype in product_claim_types and value and not has_explicit_ticket_price_signal(price_blob):
                evidence_has_product = True
                if value not in product_candidates:
                    product_candidates.append(value)
            if ctype == "platform_ticket_url" and value.startswith("http") and value not in detail_urls:
                detail_urls.append(value)
        if evidence_has_product and ev.source_url and ev.source_url.startswith("http"):
            if ev.source_url not in detail_urls:
                detail_urls.append(ev.source_url)

    if price_found or not product_candidates:
        return None

    finding = {
        "type": "structured_ticket_product_without_price",
        "claim_type": claim_type,
        "product_candidates": product_candidates[:8],
        "detail_urls": detail_urls[:8],
    }
    evidence_gap = {
        "missing_evidence_need": "ticket_product_price",
        "price_lookup_mode": "ticket_product_detail",
        "product_candidates": product_candidates[:8],
        "detail_urls": detail_urls[:8],
        "require_price_fields": True,
    }
    return {
        "reason": "structured_ticket_product_without_price",
        "hook_findings": [finding],
        "evidence_gap": evidence_gap,
    }


TICKET_GAP_FILL_TOOLS: list[str] = [
    "official_source_discovery_mcp",
    "official_page_reader_mcp",
    "search_mcp",
    "browser_mcp",
    "baidu_place_detail_mcp",
    "fliggy_ticket_api_mcp",
    "ticketlens_experience_mcp",
    "ctrip_ticket_signal_crawler_mcp",
    "dianping_ticket_signal_crawler_mcp",
]

TICKET_BOOKING_PRIMARY_TOOLS: list[str] = [
    "official_source_discovery_mcp",
    "official_page_reader_mcp",
    "search_mcp",
    "browser_mcp",
    "baidu_place_detail_mcp",
    "fliggy_ticket_api_mcp",
    "ticketlens_experience_mcp",
    "ctrip_ticket_signal_crawler_mcp",
    "dianping_ticket_signal_crawler_mcp",
]
