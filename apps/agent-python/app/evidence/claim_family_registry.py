"""Compatibility metadata for managed attraction fact families."""

from __future__ import annotations

from dataclasses import dataclass


CLAIM_TYPE_TO_FAMILY: dict[str, str] = {
    "ticket_price": "managed_fact",
    "opening_hours": "managed_fact",
    "temporary_closure": "managed_fact",
    "visitor_notice": "managed_fact",
    "accessibility": "managed_fact",
    "general_description": "managed_fact",
    "seasonality": "managed_fact",
    "reservation_policy": "managed_fact",
    "entity_resolution": "entity_identity",
    "place_identity": "entity_identity",
    "comparison": "comparison",
}


@dataclass(frozen=True)
class ClaimFamilySpec:
    claim_family: str
    extraction_schema: str | None = None
    default_source_families: tuple[str, ...] = ()
    claim_types: tuple[str, ...] = ()


FAMILY_SPECS = {
    "managed_fact": ClaimFamilySpec(
        claim_family="managed_fact",
        default_source_families=("knowledge_base", "official_source"),
        claim_types=tuple(
            claim for claim, family in CLAIM_TYPE_TO_FAMILY.items() if family == "managed_fact"
        ),
    ),
    "entity_identity": ClaimFamilySpec(
        claim_family="entity_identity",
        default_source_families=("knowledge_base",),
        claim_types=("entity_resolution", "place_identity"),
    ),
}

CLAIM_TYPE_ALIASES = {
    claim: frozenset({claim}) for claim in CLAIM_TYPE_TO_FAMILY
}


def claim_family_for_type(claim_type: str) -> str:
    return CLAIM_TYPE_TO_FAMILY.get(claim_type, "managed_fact")


def family_spec(claim_family: str) -> ClaimFamilySpec | None:
    return FAMILY_SPECS.get(claim_family)


def preferred_source_families_for(claim_type: str) -> list[str]:
    spec = family_spec(claim_family_for_type(claim_type))
    return list(spec.default_source_families) if spec else ["knowledge_base"]


def preferred_tools_for_claim(claim_type: str) -> list[str]:
    del claim_type
    return ["hybrid_retrieval", "official_page_reader_mcp"]


def extraction_schema_for(claim_type: str) -> str | None:
    spec = family_spec(claim_family_for_type(claim_type))
    return spec.extraction_schema if spec else None


def ticket_claim_types() -> frozenset[str]:
    return frozenset({"ticket_price"})
