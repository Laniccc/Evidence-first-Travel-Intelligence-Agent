"""Bridge official-source discovery candidates into S5 URL inputs and structured state."""

from __future__ import annotations

from typing import Any

from app.evidence.official_source_judgement import (
    best_official_support,
    iter_official_candidates,
    judge_candidate_for_claim,
    source_class_priority,
)
from app.evidence.official_source import OfficialSourceCandidate
from tools.official_source.url_normalizer import filter_readable_page_urls, is_official_reader_url, is_readable_page_url
from tools.official_source.whitelist_resolver import resolve_official_whitelist_url


def harvest_official_candidates(evidence: list) -> list[tuple[str, OfficialSourceCandidate]]:
    return iter_official_candidates(evidence)


def _candidate_record(evidence_id: str, cand: OfficialSourceCandidate) -> dict:
    return {
        "evidence_id": evidence_id,
        "url": cand.url,
        "domain": cand.domain,
        "title": cand.title,
        "source_class": cand.source_class,
        "official_confidence": cand.official_confidence,
        "has_ticket_info": cand.has_ticket_info,
        "has_opening_hours": cand.has_opening_hours,
        "has_notice_info": cand.has_notice_info,
        "claim_relevance_hints": dict(cand.claim_relevance_hints or {}),
        "supports_claim_types": list(cand.supports_claim_types or []),
    }


def sync_official_candidates_to_structured(state: Any) -> None:
    """Persist discovery candidates for gap-fill / page-reader preconditions."""
    rows: list[dict] = []
    seen_urls: set[str] = set()
    for ev_id, cand in harvest_official_candidates(list(state.evidence or [])):
        url = str(cand.url or "").strip()
        key = url.rstrip("/") if url else f"{cand.domain}:{cand.source_class}"
        if key in seen_urls:
            continue
        seen_urls.add(key)
        rows.append(_candidate_record(ev_id, cand))
    rows.sort(
        key=lambda row: (
            -float(row.get("official_confidence") or 0),
            source_class_priority(str(row.get("source_class") or "")),
        )
    )
    structured = dict(state.structured_result or {})
    if rows:
        structured["official_source_candidates"] = rows
    elif structured.get("official_source_candidates"):
        pass
    else:
        structured.pop("official_source_candidates", None)
    state.structured_result = structured


def best_official_url(state: Any, claim_type: str | None = None) -> str | None:
    need = claim_type or _primary_fact_need_from_state(state)
    support = best_official_support(list(state.evidence or []), need)
    cand = support.best_candidate
    if not cand:
        return None
    url = str(cand.url or "").strip()
    if url and is_official_reader_url(url):
        return url
    return None


def _ranked_candidate_urls(state: Any, claim_type: str) -> list[str]:
    ranked: list[tuple[int, float, str]] = []
    tier_rank = {"strong": 3, "partial": 2, "weak": 1, "none": 0}
    for _ev_id, cand in harvest_official_candidates(list(state.evidence or [])):
        url = str(cand.url or "").strip()
        if not url or not is_official_reader_url(url):
            continue
        judgement = judge_candidate_for_claim(cand, claim_type)
        ranked.append(
            (
                tier_rank.get(judgement.coverage_tier, 0),
                float(cand.official_confidence or 0),
                url,
            )
        )
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    out: list[str] = []
    for _tier, _conf, url in ranked:
        if url not in out:
            out.append(url)
    structured = state.structured_result or {}
    for row in structured.get("official_source_candidates") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if url and is_official_reader_url(url) and url not in out:
            out.append(url)
    return out


def collect_readable_urls_for_claim(
    state: Any,
    claim_type: str | None = None,
) -> list[str]:
    """Ordered fetchable URLs: discovery candidates → evidence pick → search → whitelist."""
    need = claim_type or _primary_fact_need_from_state(state)
    urls: list[str] = []

    def _add(url: str | None) -> None:
        if not url:
            return
        u = str(url).strip()
        if u.startswith("http") and u not in urls and is_official_reader_url(u):
            urls.append(u)

    for url in _ranked_candidate_urls(state, need):
        _add(url)

    from tools.mcp.adapters.page_content_extractor import pick_url_from_evidence

    picked = pick_url_from_evidence(list(state.evidence or []), prefer_official=True)
    _add(picked)

    place = _resolved_place_label(state)
    _add(resolve_official_whitelist_url(place))

    return urls


def has_readable_url_inputs(state: Any, claim_type: str | None = None) -> bool:
    return bool(collect_readable_urls_for_claim(state, claim_type))


_FACT_NEEDS = frozenset(
    {
        "ticket_price",
        "opening_hours",
        "elevation",
        "reservation_policy",
        "temporary_closure",
        "seasonal_operation_status",
        "road_opening_period",
    }
)


def _primary_fact_need_from_state(state: Any) -> str:
    for attr_name in ("evidence_gap", "response_contract", "user_need_residual"):
        value = getattr(state, attr_name, None)
        requirements = getattr(value, "claim_requirements", None) or []
        for requirement in requirements:
            claim_type = str(getattr(requirement, "claim_type", "") or "")
            if claim_type in _FACT_NEEDS:
                return claim_type
    frame = getattr(state, "semantic_frame", None)
    for need in getattr(frame, "information_needs", None) or []:
        value = str(getattr(need, "need_type", need) or "")
        if value in _FACT_NEEDS:
            return value
    text = " ".join(
        str(getattr(state, name, "") or "")
        for name in ("raw_user_query", "normalized_request")
    )
    if any(token in text for token in ("门票", "票价", "多少钱")):
        return "ticket_price"
    if any(token in text for token in ("开放", "营业时间", "几点")):
        return "opening_hours"
    if "海拔" in text:
        return "elevation"
    if "预约" in text:
        return "reservation_policy"
    return "general_fact"


def _resolved_place_label(state: Any) -> str:
    structured = getattr(state, "structured_result", None) or {}
    anchor = structured.get("fact_anchor") or {}
    for value in (
        anchor.get("resolved_name"),
        anchor.get("raw_place"),
        getattr(getattr(state, "place_context", None), "resolved_name", None),
        getattr(state, "raw_user_query", None),
    ):
        label = str(value or "").strip()
        if label:
            return label
    frame = getattr(state, "semantic_frame", None)
    entities = getattr(frame, "entities", None)
    places = getattr(entities, "places", None) or []
    return str(places[0] if places else "").strip()
