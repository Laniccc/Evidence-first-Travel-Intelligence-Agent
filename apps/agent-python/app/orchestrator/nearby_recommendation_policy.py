"""S5/S7/S8 policy for nearby_recommendation task family (food, toilet, parking, …)."""

from __future__ import annotations

from app.orchestrator.information_need_aliases import (
    is_nearby_need,
    normalize_need,
    resolve_nearby_need,
)
from app.orchestrator.nearby_category_registry import (
    NEARBY_CATEGORIES,
    actionable_types_for_category,
    baidu_tag_for_category,
    is_adoptable_for_category,
    label_for_category,
    primary_claim_type_for_category,
    query_suffix_for_category,
    s8_focus_for_category,
    scorable_types_for_category,
)
from app.schemas.evidence import Claim, ClaimType

# Backward-compatible exports
BAIDU_TAG_BY_NEED = {c.canonical_need: c.baidu_tag for c in NEARBY_CATEGORIES}

NEARBY_NEED_LABELS = {c.canonical_need: c.label for c in NEARBY_CATEGORIES}
NEARBY_NEED_LABELS.update(
    {
        "restaurant_recommendation": "周边美食",
        "nearby_accommodation": "周边住宿",
        "nearby_amenity": "周边设施",
        "lodging_area": "周边住宿",
    }
)

NEARBY_QUERY_SUFFIX_BY_NEED = {c.canonical_need: c.query_suffix for c in NEARBY_CATEGORIES}


def is_nearby_information_need(need: str | None) -> bool:
    return is_nearby_need(str(need or ""))


def baidu_tag_for_need(need: str | None) -> str | None:
    canonical = resolve_nearby_need(str(need or ""))
    return baidu_tag_for_category(canonical)


def nearby_query_suffix_for_need(need: str | None) -> str:
    canonical = resolve_nearby_need(str(need or ""))
    return query_suffix_for_category(canonical)


def nearby_need_label(need: str) -> str:
    canonical = normalize_need(need)
    return NEARBY_NEED_LABELS.get(canonical, label_for_category(canonical))


def claim_aliases_for_need(need: str) -> frozenset[str]:
    """S7 EvidenceScorer aliases for a nearby information_need."""
    canonical = resolve_nearby_need(need)
    return scorable_types_for_category(canonical)


def s8_focus_claim_types(need: str) -> frozenset[str]:
    """Map information_need (e.g. nearby_food) to evidence claim_type strings for S8 clues."""
    canonical = resolve_nearby_need(need)
    return s8_focus_for_category(canonical)


def s8_focus_claim_types_for_needs(needs: set[str]) -> set[str]:
    out: set[str] = set()
    for need in needs:
        if is_nearby_information_need(need):
            out.update(s8_focus_claim_types(need))
    return out


def actionable_claim_types_for_need(need: str) -> frozenset[str]:
    canonical = resolve_nearby_need(need)
    return actionable_types_for_category(canonical)


def actionable_claim_types_for_needs(needs: set[str]) -> set[str]:
    out: set[str] = set()
    for need in needs:
        if is_nearby_information_need(need):
            out.update(actionable_claim_types_for_need(need))
    return out


def extract_poi_name_from_claim_value(value: str) -> str:
    text = (value or "").strip()
    for sep in ("（", "("):
        if sep in text:
            return text.split(sep, 1)[0].strip()
    return text


def is_adoptable_nearby_poi(
    name: str,
    need: str,
    *,
    anchor_place: str = "",
    poi_tag: str | None = None,
    search_tag: str | None = None,
) -> bool:
    """Filter map POIs so lodging/food/etc. claims do not include anchor sub-POIs or wrong categories."""
    canonical = resolve_nearby_need(need)
    return is_adoptable_for_category(
        name,
        canonical,
        anchor_place=anchor_place,
        poi_tag=poi_tag,
        search_tag=search_tag,
    )


def place_candidates_is_nearby_recommendation(claim: Claim) -> bool:
    """True when PLACE_CANDIDATES came from a nearby circle search, not anchor resolution."""
    if claim.claim_type != ClaimType.PLACE_CANDIDATES:
        return False
    nv = claim.normalized_value
    if isinstance(nv, dict) and nv.get("retrieval_context") == "nearby_recommendation":
        return True
    return False


def format_nearby_clue_text(
    claim: Claim,
    *,
    question_label: str,
    reputation: dict | None = None,
) -> str:
    value = str(claim.value or "").strip()
    if not value:
        return ""
    if claim.claim_type == ClaimType.PLACE_CANDIDATES:
        return ""
    label = question_label or nearby_need_label(
        str((claim.normalized_value or {}).get("information_need") or "nearby_poi")
        if isinstance(claim.normalized_value, dict)
        else "nearby_poi"
    )
    nv = claim.normalized_value if isinstance(claim.normalized_value, dict) else {}
    rep = reputation or {}
    rating = nv.get("rating") if nv.get("rating") is not None else rep.get("rating")
    review_count = nv.get("review_count") if nv.get("review_count") is not None else rep.get("review_count")
    if rating is not None and claim.claim_type in {ClaimType.FOOD, ClaimType.RATING_CANDIDATE, ClaimType.LODGING}:
        extra = f"（评分 {rating}"
        if review_count:
            extra += f"，{review_count}条评价"
        extra += "）"
        if extra.strip("（）") not in value:
            value = f"{value}{extra}"
    review_snippet = rep.get("review_snippet")
    if review_snippet and claim.claim_type in {ClaimType.FOOD, ClaimType.LODGING}:
        snippet = str(review_snippet).strip()
        if snippet and snippet not in value:
            short = snippet if len(snippet) <= 120 else snippet[:117] + "…"
            value = f"{value} — {short}"
    return f"{label}：{value}"


def primary_claim_type_for_need(need: str) -> ClaimType:
    raw = primary_claim_type_for_category(resolve_nearby_need(need))
    return ClaimType(raw)
