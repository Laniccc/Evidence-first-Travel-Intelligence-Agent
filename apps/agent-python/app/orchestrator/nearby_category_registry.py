"""Single source of truth for nearby POI categories: Baidu open/poitags taxonomy."""

from __future__ import annotations

import re

from app.orchestrator.baidu_poi_taxonomy import (
    BaiduTaxonomyEntry,
    get_taxonomy_entry,
    infer_all_needs_from_text as _taxonomy_infer_all,
    infer_primary_need_from_text as _taxonomy_infer_primary,
    load_taxonomy_entries,
    tag_matches_entry,
    taxonomy_metadata_for_need,
)
from app.schemas.evidence import ClaimType

_DEFAULT_ACTIONABLE = frozenset(
    {
        ClaimType.GENERAL_FACT.value,
        ClaimType.PLACE_CANDIDATES.value,
        ClaimType.ADDRESS.value,
        ClaimType.RATING_CANDIDATE.value,
    }
)

_DEFAULT_S8_FOCUS = frozenset(
    {
        ClaimType.GENERAL_FACT.value,
        ClaimType.PLACE_CANDIDATES.value,
        ClaimType.ADDRESS.value,
    }
)

_ANCHOR_SUBPOI = re.compile(r"东门|西门|南门|北门|停车场|地上停车场|地下停车场|校门|出入口")
_SCHOOL = re.compile(r"中学|小学|大学|学校|校区|学院|实验校")

_GF = frozenset(
    {
        ClaimType.FOOD.value,
        ClaimType.PLACE_CANDIDATES.value,
        ClaimType.ADDRESS.value,
        ClaimType.RATING_CANDIDATE.value,
        ClaimType.GENERAL_FACT.value,
    }
)
_GH = frozenset(
    {
        ClaimType.LODGING.value,
        ClaimType.PLACE_CANDIDATES.value,
        ClaimType.ADDRESS.value,
        ClaimType.RATING_CANDIDATE.value,
        ClaimType.GENERAL_FACT.value,
    }
)
_GA = frozenset({ClaimType.GENERAL_FACT.value, ClaimType.PLACE_CANDIDATES.value, ClaimType.ADDRESS.value})


class NearbyCategory:
    """Runtime view of a Baidu taxonomy entry for S5/S7/S8 policy."""

    __slots__ = (
        "canonical_need",
        "inference_pattern",
        "inference_priority",
        "baidu_tag",
        "query_suffix",
        "label",
        "primary_claim_type",
        "actionable_claim_types",
        "s8_focus_claim_types",
        "scorable_claim_types",
        "name_markers",
        "tag_markers",
        "brand_allowlist",
        "strict_filter",
        "baidu_primary_industry",
        "baidu_secondary_tags",
        "adopt_tags",
        "is_generic_fallback",
        "enrichment_claim_types",
        "enrichment_tools",
        "enrichment_top_n",
        "review_enrichment_top_n",
    )

    def __init__(self, entry: BaiduTaxonomyEntry) -> None:
        self.canonical_need = entry.canonical_need
        self.inference_priority = entry.inference_priority
        self.baidu_tag = entry.search_tag
        self.query_suffix = entry.query_suffix
        self.label = entry.label
        self.primary_claim_type = entry.primary_claim_type
        self.name_markers = entry.name_markers
        self.tag_markers = entry.tag_markers
        self.brand_allowlist = entry.brand_allowlist
        self.strict_filter = entry.strict_filter
        self.baidu_primary_industry = entry.baidu_primary_industry
        self.baidu_secondary_tags = entry.baidu_secondary_tags
        self.adopt_tags = entry.adopt_tags
        self.is_generic_fallback = entry.is_generic_fallback
        self.enrichment_claim_types = entry.enrichment_claim_types
        self.enrichment_tools = entry.enrichment_tools
        self.enrichment_top_n = entry.enrichment_top_n
        self.review_enrichment_top_n = entry.review_enrichment_top_n
        kws = [re.escape(k) for k in entry.inference_keywords if k]
        self.inference_pattern = (
            re.compile("|".join(kws), re.I) if kws else re.compile(r"$^")
        )
        if entry.primary_claim_type == ClaimType.FOOD.value:
            self.actionable_claim_types = frozenset(
                {ClaimType.FOOD.value, ClaimType.RATING_CANDIDATE.value}
            )
            self.s8_focus_claim_types = frozenset(
                {ClaimType.FOOD.value, ClaimType.GENERAL_FACT.value, ClaimType.PLACE_CANDIDATES.value}
            )
            self.scorable_claim_types = _GF | frozenset({entry.canonical_need})
        elif entry.primary_claim_type == ClaimType.LODGING.value:
            self.actionable_claim_types = frozenset(
                {ClaimType.LODGING.value, ClaimType.RATING_CANDIDATE.value}
            )
            self.s8_focus_claim_types = frozenset(
                {ClaimType.LODGING.value, ClaimType.GENERAL_FACT.value, ClaimType.PLACE_CANDIDATES.value}
            )
            self.scorable_claim_types = _GH | frozenset({entry.canonical_need})
        else:
            self.actionable_claim_types = _GA
            self.s8_focus_claim_types = (
                frozenset({ClaimType.GENERAL_FACT.value, ClaimType.ADDRESS.value})
                if entry.strict_filter
                else _GA
            )
            self.scorable_claim_types = _DEFAULT_ACTIONABLE | frozenset({entry.canonical_need})


def _build_categories() -> tuple[NearbyCategory, ...]:
    return tuple(NearbyCategory(e) for e in load_taxonomy_entries())


NEARBY_CATEGORIES: tuple[NearbyCategory, ...] = _build_categories()
_BY_NEED: dict[str, NearbyCategory] = {c.canonical_need: c for c in NEARBY_CATEGORIES}
_SORTED = tuple(sorted(NEARBY_CATEGORIES, key=lambda c: c.inference_priority))

CANONICAL_NEARBY_NEEDS = frozenset(_BY_NEED.keys())

NEED_ALIASES: dict[str, str] = {
    "nearby_dining": "nearby_food",
    "nearby_restaurant": "nearby_food",
    "restaurant_recommendation": "nearby_food",
    "food_recommendation": "nearby_food",
    "food_nearby": "nearby_food",
    "nearby_lodging": "nearby_hotel",
    "nearby_accommodation": "nearby_hotel",
    "nearby_attraction": "nearby_scenic",
    "nearby_places": "nearby_poi",
    "nearby_gas_station": "nearby_gas",
    "nearby_charging_station": "nearby_charging",
}

GENERIC_NEARBY_NEEDS = frozenset(
    {
        "nearby_amenity",
        "amenity_nearby",
        "public_amenity",
        "nearby_facility",
        "nearby_facilities",
    }
)


def normalize_canonical_need(need: str) -> str:
    return NEED_ALIASES.get(need, need)


def get_category(need: str) -> NearbyCategory | None:
    return _BY_NEED.get(normalize_canonical_need(need))


def infer_nearby_need_from_text(text: str) -> str:
    return _taxonomy_infer_primary(text)


def infer_all_nearby_needs_from_text(text: str) -> list[str]:
    return _taxonomy_infer_all(text)


def baidu_tag_for_category(need: str) -> str | None:
    cat = get_category(need)
    return cat.baidu_tag if cat else None


def query_suffix_for_category(need: str) -> str:
    cat = get_category(need)
    return cat.query_suffix if cat else "周边"


def label_for_category(need: str) -> str:
    cat = get_category(need)
    return cat.label if cat else normalize_canonical_need(need).replace("_", " ")


def primary_claim_type_for_category(need: str) -> str:
    cat = get_category(need)
    return cat.primary_claim_type if cat else ClaimType.GENERAL_FACT.value


def actionable_types_for_category(need: str) -> frozenset[str]:
    cat = get_category(need)
    return cat.actionable_claim_types if cat else _DEFAULT_S8_FOCUS


def s8_focus_for_category(need: str) -> frozenset[str]:
    cat = get_category(need)
    return cat.s8_focus_claim_types if cat else _DEFAULT_S8_FOCUS


def scorable_types_for_category(need: str) -> frozenset[str]:
    cat = get_category(need)
    return cat.scorable_claim_types if cat else _DEFAULT_ACTIONABLE


def enrichment_enabled_for_category(need: str) -> bool:
    cat = get_category(need)
    return bool(cat and cat.enrichment_tools and cat.enrichment_top_n > 0)


def enrichment_tools_for_category(need: str) -> tuple[str, ...]:
    cat = get_category(need)
    return cat.enrichment_tools if cat else ()


def enrichment_top_n_for_category(need: str) -> int:
    cat = get_category(need)
    return cat.enrichment_top_n if cat else 0


def review_enrichment_top_n_for_category(need: str) -> int:
    cat = get_category(need)
    return cat.review_enrichment_top_n if cat else 0


def taxonomy_meta_for_need(need: str) -> dict[str, str]:
    return taxonomy_metadata_for_need(normalize_canonical_need(need))


def _tag_matches_category(tag: str | None, cat: NearbyCategory) -> bool:
    if not tag:
        return False
    entry = get_taxonomy_entry(cat.canonical_need)
    if entry and tag_matches_entry(tag, entry):
        return True
    if cat.tag_markers:
        return bool(cat.tag_markers.search(str(tag)))
    return any(marker in str(tag) for marker in cat.adopt_tags)


def _name_matches_category(name: str, cat: NearbyCategory) -> bool:
    if not cat.name_markers:
        return True
    if cat.canonical_need == "nearby_food":
        return bool(cat.name_markers.search(name)) and not _SCHOOL.search(name)
    return bool(cat.name_markers.search(name))


def _brand_matches_category(name: str, cat: NearbyCategory) -> bool:
    if not cat.brand_allowlist:
        return False
    return any(brand in name for brand in cat.brand_allowlist)


def _tag_conflicts_category(tag: str | None, cat: NearbyCategory) -> bool:
    if not tag:
        return False
    t = str(tag)
    for other in NEARBY_CATEGORIES:
        if other.canonical_need == cat.canonical_need or other.is_generic_fallback:
            continue
        if other.strict_filter and _tag_matches_category(t, other):
            if not _tag_matches_category(t, cat):
                return True
    return False


def is_adoptable_for_category(
    name: str,
    need: str,
    *,
    anchor_place: str = "",
    poi_tag: str | None = None,
    search_tag: str | None = None,
) -> bool:
    n = (name or "").strip()
    if not n:
        return False
    cat = get_category(normalize_canonical_need(need))
    if not cat:
        return True

    effective_item_tag = poi_tag

    if cat.canonical_need == "nearby_food":
        if _ANCHOR_SUBPOI.search(n) and not _name_matches_category(n, cat):
            return False
        if anchor_place:
            anchor_core = anchor_place.split("(")[0].strip()
            if anchor_core and anchor_core in n and _SCHOOL.search(n) and not _name_matches_category(n, cat):
                return False
        if _tag_matches_category(effective_item_tag, cat):
            return True
        if _name_matches_category(n, cat):
            return True
        return True

    if cat.is_generic_fallback:
        if _ANCHOR_SUBPOI.search(n) and not _name_matches_category(n, cat):
            return False
        return True

    if _ANCHOR_SUBPOI.search(n) and not (
        _name_matches_category(n, cat)
        or _brand_matches_category(n, cat)
        or _tag_matches_category(effective_item_tag, cat)
    ):
        return False

    if anchor_place:
        anchor_core = anchor_place.split("(")[0].strip()
        if anchor_core and anchor_core in n and _SCHOOL.search(n):
            if not (
                _name_matches_category(n, cat)
                or _brand_matches_category(n, cat)
                or _tag_matches_category(effective_item_tag, cat)
            ):
                return False
        if n == anchor_place or n.startswith(anchor_place):
            if not (
                _name_matches_category(n, cat)
                or _brand_matches_category(n, cat)
                or _tag_matches_category(effective_item_tag, cat)
            ):
                return False

    if _tag_conflicts_category(effective_item_tag, cat):
        return False

    if _tag_matches_category(effective_item_tag, cat):
        return True
    if _brand_matches_category(n, cat):
        return True
    if _name_matches_category(n, cat):
        return True

    if cat.strict_filter:
        return False

    return True
