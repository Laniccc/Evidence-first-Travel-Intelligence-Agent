"""Baidu Map POI industry taxonomy (open/poitags) for nearby_recommendation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_COMPOUND_SPLIT = re.compile(r"[,，、]|(?:和|以及|还有|顺便|同时|跟)")
_NEARBY_CONTEXT = re.compile(r"附近|周边|顺路", re.I)

_TAXONOMY_PATH = Path(__file__).resolve().parent / "data" / "baidu_nearby_taxonomy.json"


@dataclass(frozen=True)
class BaiduTaxonomyEntry:
    canonical_need: str
    baidu_primary_industry: str
    baidu_secondary_tags: frozenset[str]
    search_tag: str | None
    query_suffix: str
    adopt_tags: frozenset[str]
    label: str
    inference_priority: int
    inference_keywords: tuple[str, ...]
    name_markers: re.Pattern | None
    tag_markers: re.Pattern | None
    brand_allowlist: frozenset[str] = field(default_factory=frozenset)
    primary_claim_type: str = "general_fact"
    strict_filter: bool = False
    is_generic_fallback: bool = False
    enrichment_claim_types: frozenset[str] = field(default_factory=frozenset)
    enrichment_tools: tuple[str, ...] = ()
    enrichment_top_n: int = 0
    review_enrichment_top_n: int = 0


def _compile_pattern(raw: str | None) -> re.Pattern | None:
    if not raw:
        return None
    return re.compile(raw, re.I)


def _entry_from_raw(raw: dict[str, Any]) -> BaiduTaxonomyEntry:
    keywords = tuple(str(k).strip() for k in (raw.get("inference_keywords") or []) if str(k).strip())
    brands = frozenset(str(b) for b in (raw.get("brand_allowlist") or []))
    adopt = frozenset(str(t) for t in (raw.get("adopt_tags") or []) if str(t).strip())
    secondary = frozenset(str(t) for t in (raw.get("baidu_secondary_tags") or []) if str(t).strip())
    tag = raw.get("search_tag")
    return BaiduTaxonomyEntry(
        canonical_need=str(raw["canonical_need"]),
        baidu_primary_industry=str(raw.get("baidu_primary_industry") or ""),
        baidu_secondary_tags=secondary,
        search_tag=str(tag) if tag else None,
        query_suffix=str(raw.get("query_suffix") or "周边"),
        adopt_tags=adopt,
        label=str(raw.get("label") or raw["canonical_need"]),
        inference_priority=int(raw.get("inference_priority") or 500),
        inference_keywords=keywords,
        name_markers=_compile_pattern(raw.get("name_markers")),
        tag_markers=_compile_pattern(raw.get("tag_markers")),
        brand_allowlist=brands,
        primary_claim_type=str(raw.get("primary_claim_type") or "general_fact"),
        strict_filter=bool(raw.get("strict_filter")),
        is_generic_fallback=bool(raw.get("is_generic_fallback")),
        enrichment_claim_types=frozenset(
            str(t) for t in (raw.get("enrichment_claim_types") or []) if str(t).strip()
        ),
        enrichment_tools=tuple(
            str(t) for t in (raw.get("enrichment_tools") or []) if str(t).strip()
        ),
        enrichment_top_n=int(raw.get("enrichment_top_n") or 0),
        review_enrichment_top_n=int(raw.get("review_enrichment_top_n") or 0),
    )


@lru_cache(maxsize=1)
def load_taxonomy_entries() -> tuple[BaiduTaxonomyEntry, ...]:
    data = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
    entries = tuple(_entry_from_raw(row) for row in data.get("entries") or [])
    return tuple(sorted(entries, key=lambda e: e.inference_priority))


@lru_cache(maxsize=1)
def taxonomy_by_need() -> dict[str, BaiduTaxonomyEntry]:
    return {e.canonical_need: e for e in load_taxonomy_entries()}


def get_taxonomy_entry(need: str) -> BaiduTaxonomyEntry | None:
    return taxonomy_by_need().get(need)


def taxonomy_metadata_for_need(need: str) -> dict[str, str]:
    entry = get_taxonomy_entry(need)
    if not entry:
        return {}
    meta: dict[str, str] = {
        "taxonomy_schema": "baidu_poitags_v1",
        "baidu_primary_industry": entry.baidu_primary_industry,
    }
    if entry.baidu_secondary_tags:
        meta["baidu_secondary_tags"] = ",".join(sorted(entry.baidu_secondary_tags))
    if entry.search_tag:
        meta["search_tag"] = entry.search_tag
    return meta


def _keyword_hits(segment: str, entry: BaiduTaxonomyEntry) -> list[str]:
    hits: list[str] = []
    seg_lower = segment.lower()
    for kw in entry.inference_keywords:
        k = kw.lower()
        if k in seg_lower or (len(kw) >= 2 and kw in segment):
            hits.append(kw)
    return hits


def _best_entry_for_segment(segment: str) -> BaiduTaxonomyEntry | None:
    best: BaiduTaxonomyEntry | None = None
    best_score = -1
    for entry in load_taxonomy_entries():
        if entry.is_generic_fallback:
            continue
        hits = _keyword_hits(segment, entry)
        if not hits:
            continue
        score = max(len(h) for h in hits) * 100 - entry.inference_priority
        if score > best_score:
            best_score = score
            best = entry
    return best


def infer_primary_need_from_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "nearby_poi"
    segments = [s.strip() for s in _COMPOUND_SPLIT.split(t) if s.strip()] or [t]
    for segment in segments:
        hit = _best_entry_for_segment(segment)
        if hit:
            return hit.canonical_need
    for entry in load_taxonomy_entries():
        if entry.is_generic_fallback:
            continue
        if any(kw.lower() in t.lower() for kw in entry.inference_keywords):
            return entry.canonical_need
    if _NEARBY_CONTEXT.search(t):
        return "nearby_poi"
    return "nearby_poi"


def infer_all_needs_from_text(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return ["nearby_poi"]

    segments = [s.strip() for s in _COMPOUND_SPLIT.split(t) if s.strip()] or [t]
    matched: list[str] = []
    seen: set[str] = set()

    for segment in segments:
        hit = _best_entry_for_segment(segment)
        if hit and hit.canonical_need not in seen:
            seen.add(hit.canonical_need)
            matched.append(hit.canonical_need)

    if not matched:
        for entry in load_taxonomy_entries():
            if entry.is_generic_fallback:
                continue
            if any(kw.lower() in t.lower() for kw in entry.inference_keywords):
                if entry.canonical_need not in seen:
                    seen.add(entry.canonical_need)
                    matched.append(entry.canonical_need)

    if not matched and _NEARBY_CONTEXT.search(t):
        return ["nearby_poi"]
    if not matched:
        return ["nearby_poi"]
    return matched


def tag_matches_entry(tag: str | None, entry: BaiduTaxonomyEntry) -> bool:
    if not tag:
        return False
    t = str(tag)
    if entry.baidu_primary_industry and entry.baidu_primary_industry in t:
        return True
    if any(sec in t for sec in entry.baidu_secondary_tags):
        return True
    if entry.tag_markers and entry.tag_markers.search(t):
        return True
    return any(marker in t for marker in entry.adopt_tags)
