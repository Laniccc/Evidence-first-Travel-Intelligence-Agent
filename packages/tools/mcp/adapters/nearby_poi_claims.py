"""Emit typed nearby-recommendation claims from Baidu place_search results (tools layer)."""

from __future__ import annotations

from typing import Any

from app.orchestrator.information_need_aliases import normalize_need, resolve_nearby_need
from app.orchestrator.nearby_category_registry import CANONICAL_NEARBY_NEEDS, primary_claim_type_for_category, taxonomy_meta_for_need
from app.orchestrator.nearby_recommendation_policy import is_adoptable_nearby_poi
from app.schemas.evidence import Claim, ClaimType


def normalize_nearby_need(need: str | None) -> str:
    raw = (need or "").strip()
    if not raw:
        return ""
    return normalize_need(raw)


def is_nearby_information_need(need: str | None) -> bool:
    return normalize_nearby_need(need) in CANONICAL_NEARBY_NEEDS


def is_nearby_retrieval(
    *,
    information_need: str | None = None,
    claim_target: str | None = None,
    nearby_search: bool = False,
    tag: str | None = None,
    latitude: Any = None,
) -> bool:
    need = normalize_nearby_need(information_need or claim_target)
    if is_nearby_information_need(need):
        return True
    if nearby_search:
        return True
    if tag and latitude is not None:
        return True
    return False


def primary_claim_type_for_need(need: str) -> ClaimType:
    canonical = resolve_nearby_need(need)
    return ClaimType(primary_claim_type_for_category(canonical))


def format_nearby_poi_value(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    address = str(item.get("address") or "").strip()
    if name and address:
        return f"{name}（{address}）"
    return name or address


def tag_place_candidates_as_nearby(
    claims: list[Claim],
    *,
    information_need: str,
    candidates: list[dict[str, Any]],
    search_tag: str | None = None,
) -> None:
    need = normalize_nearby_need(information_need)
    for claim in claims:
        if claim.claim_type != ClaimType.PLACE_CANDIDATES:
            continue
        nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
        claim.normalized_value = {
            **nv,
            "candidates": nv.get("candidates") or candidates,
            "retrieval_context": "nearby_recommendation",
            "information_need": need,
            "search_tag": search_tag,
        }


def append_nearby_recommendation_claims(
    claims: list[Claim],
    candidates: list[dict[str, Any]],
    information_need: str,
    *,
    anchor_location_key: str = "",
    anchor_candidate_name: str = "",
    search_tag: str | None = None,
) -> list[Claim]:
    """Add per-POI typed claims for S7 nearby_recommendation scoring."""
    need = normalize_nearby_need(information_need) or "nearby_poi"
    primary = primary_claim_type_for_need(need)
    tag_place_candidates_as_nearby(
        claims, information_need=need, candidates=candidates, search_tag=search_tag
    )
    anchor_meta = {
        "information_need": need,
        "search_tag": search_tag,
        "retrieval_context": "nearby_recommendation",
        "anchor_location_key": anchor_location_key,
        "anchor_candidate_name": anchor_candidate_name,
        **taxonomy_meta_for_need(need),
    }
    for item in candidates[:12]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        item_tag = item.get("tag") or item.get("type")
        if not is_adoptable_nearby_poi(
            name,
            need,
            anchor_place=anchor_candidate_name,
            poi_tag=item_tag,
            search_tag=search_tag,
        ):
            continue
        claims.append(
            Claim(
                claim_type=primary,
                value=format_nearby_poi_value(item),
                normalized_value={
                    **item,
                    **anchor_meta,
                    "baidu_item_tag": item_tag,
                    "nearby_category": need,
                },
                confidence=0.68,
            )
        )
    return claims
