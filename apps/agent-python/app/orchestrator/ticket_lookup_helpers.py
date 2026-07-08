"""Ticket lookup helpers — URL harvest, aliases, source relevance."""

from __future__ import annotations

import re

from app.schemas.evidence import Evidence, SourceType
from app.schemas.user_query import TravelAgentState
from tools.official_source.url_normalizer import clean_search_hits_for_official_chain, hits_from_evidence_list

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
    from app.orchestrator.official_source_judgement import judge_candidate_for_claim, parse_candidate_from_evidence

    cand = parse_candidate_from_evidence(ev)
    if not cand:
        return False
    if cand.has_ticket_info:
        return False
    if "destination_background" in (cand.supports_claim_types or []):
        return True
    result = judge_candidate_for_claim(cand, "ticket_price")
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
