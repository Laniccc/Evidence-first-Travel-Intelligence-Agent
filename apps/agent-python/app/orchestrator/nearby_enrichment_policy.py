"""Policy helpers for nearby POI reputation enrichment (ratings / reviews)."""

from __future__ import annotations

import re
from typing import Any

from app.orchestrator.information_need_aliases import query_text_from_state, resolve_nearby_need
from app.orchestrator.nearby_category_registry import (
    enrichment_top_n_for_category,
    review_enrichment_top_n_for_category,
)
from app.orchestrator.nearby_recommendation_policy import (
    extract_poi_name_from_claim_value,
    primary_claim_type_for_need,
)
from app.schemas.evidence import ClaimType, Evidence
from app.schemas.user_query import TravelAgentState

_REPUTATION_KW = re.compile(
    r"口碑|评价|评分|好评|差评|避雷|怎么样|值得推荐|靠谱|用餐体验|点评|好吃吗|哪家好吃|口碑好|值得吃"
)

_REPUTATION_CLAIM_TYPES = frozenset({"review_summary", "rating_candidate", "review_aspect"})


def requires_nearby_reputation_signal(state: TravelAgentState) -> bool:
    """True when user or contract explicitly wants口碑/评价 beyond a bare POI list."""
    frame = state.semantic_frame
    needs = set(frame.information_needs or []) if frame else set()
    if needs & _REPUTATION_CLAIM_TYPES:
        return True
    contract = state.response_contract
    if contract:
        for req in contract.claim_requirements:
            if req.claim_type in _REPUTATION_CLAIM_TYPES:
                return True
    return bool(_REPUTATION_KW.search(query_text_from_state(state)))


def enrichment_candidates_from_evidence(
    evidence: list,
    need: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Top nearby POI rows (from map retrieval) eligible for detail/review enrichment."""
    canonical = resolve_nearby_need(need)
    primary = primary_claim_type_for_need(canonical).value
    cap = limit if limit is not None else enrichment_top_n_for_category(canonical)
    if cap <= 0:
        return []

    seen_uids: set[str] = set()
    seen_names: set[str] = set()
    out: list[dict[str, Any]] = []

    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct != primary:
                continue
            nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
            if nv.get("retrieval_context") != "nearby_recommendation":
                continue
            claim_need = resolve_nearby_need(str(nv.get("information_need") or nv.get("nearby_category") or ""))
            if claim_need != canonical:
                continue
            uid = str(nv.get("uid") or "").strip()
            name = extract_poi_name_from_claim_value(str(claim.value or ""))
            if not uid and not name:
                continue
            if uid and uid in seen_uids:
                continue
            if name and name in seen_names:
                continue
            if uid:
                seen_uids.add(uid)
            if name:
                seen_names.add(name)
            out.append(
                {
                    "uid": uid or None,
                    "name": name,
                    "city": nv.get("city") or ev.city,
                    "information_need": canonical,
                }
            )
            if len(out) >= cap:
                return out
    return out


def build_poi_reputation_index(evidence: list) -> dict[str, Any]:
    """Index ratings and review snippets by poi uid / normalized name."""
    by_uid: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}

    def _store(key_uid: str | None, key_name: str | None, patch: dict[str, Any]) -> None:
        if key_uid:
            slot = by_uid.setdefault(key_uid, {})
            slot.update({k: v for k, v in patch.items() if v is not None})
        if key_name:
            norm = key_name.strip()
            if norm:
                slot = by_name.setdefault(norm, {})
                slot.update({k: v for k, v in patch.items() if v is not None})

    for ev in evidence or []:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
            uid = str(nv.get("poi_uid") or nv.get("uid") or "").strip() or None
            name = str(
                nv.get("poi_name") or nv.get("name") or nv.get("shop_name") or ""
            ).strip() or None
            if ct == ClaimType.RATING_CANDIDATE.value:
                rating = nv.get("rating")
                if rating is None:
                    raw = str(claim.value or "")
                    m = re.search(r"([\d.]+)", raw)
                    rating = m.group(1) if m else None
                _store(
                    uid,
                    name,
                    {
                        "rating": rating,
                        "review_count": nv.get("review_count"),
                        "source_name": ev.source_name,
                    },
                )
            elif ct in {ClaimType.REVIEW_SUMMARY.value, ClaimType.REVIEW_ASPECT.value}:
                summary = str(claim.value or "").strip()
                if summary:
                    _store(uid, name, {"review_snippet": summary, "source_name": ev.source_name})

    return {"by_uid": by_uid, "by_name": by_name}


def lookup_poi_reputation(
    index: dict[str, Any],
    *,
    uid: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    by_uid = index.get("by_uid") or {}
    by_name = index.get("by_name") or {}
    if uid and uid in by_uid:
        return dict(by_uid[uid])
    if name:
        norm = name.strip()
        if norm in by_name:
            return dict(by_name[norm])
        for key, val in by_name.items():
            if norm in key or key in norm:
                return dict(val)
    return {}


def count_pois_with_reputation(
    evidence: list,
    need: str,
    *,
    top_n: int | None = None,
) -> int:
    """How many top enrichment candidates have at least rating or review evidence."""
    canonical = resolve_nearby_need(need)
    candidates = enrichment_candidates_from_evidence(evidence, canonical, limit=top_n)
    if not candidates:
        return 0
    index = build_poi_reputation_index(evidence)
    covered = 0
    for row in candidates:
        rep = lookup_poi_reputation(index, uid=row.get("uid"), name=row.get("name"))
        if rep.get("rating") is not None or rep.get("review_snippet"):
            covered += 1
    return covered


def nearby_reputation_satisfied(
    state: TravelAgentState,
    evidence: list,
    need: str,
) -> bool:
    """Reputation enrichment goal met for this nearby category."""
    if not requires_nearby_reputation_signal(state):
        return True
    canonical = resolve_nearby_need(need)
    top_n = review_enrichment_top_n_for_category(canonical) or enrichment_top_n_for_category(canonical)
    if top_n <= 0:
        return True
    candidates = enrichment_candidates_from_evidence(evidence, canonical, limit=top_n)
    if not candidates:
        return False
    covered = count_pois_with_reputation(evidence, canonical, top_n=top_n)
    minimum = min(2, len(candidates))
    return covered >= minimum


def tag_enrichment_claims(
    evidence: list,
    *,
    poi_uid: str | None,
    poi_name: str,
    information_need: str,
    enrichment_source: str,
) -> None:
    """Attach POI linkage metadata so S8 can merge ratings/reviews onto list items."""
    for ev in evidence:
        if not isinstance(ev, Evidence):
            continue
        for claim in ev.claims:
            nv = claim.normalized_value
            base = dict(nv) if isinstance(nv, dict) else {}
            base.update(
                {
                    "poi_uid": poi_uid or base.get("uid"),
                    "poi_name": poi_name,
                    "information_need": information_need,
                    "enrichment_source": enrichment_source,
                }
            )
            claim.normalized_value = base
