"""Evidence usage roles — entity anchor vs claim support."""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.evidence import ClaimType, Evidence, SourceType


@dataclass(frozen=True)
class EvidenceUsageRole:
    entity_anchor: bool = False
    claim_support: bool = False
    context_only: bool = False


def infer_evidence_usage_role(ev: Evidence, claim_type: str) -> EvidenceUsageRole:
    st = str(ev.source_type or "").lower()
    src = str(ev.source_name or "").lower()

    if claim_type in {"ticket_price", "opening_hours", "reservation_policy"}:
        for claim in ev.claims or []:
            ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
            if ct in {
                ClaimType.TICKET_PRICE.value,
                ClaimType.OPENING_HOURS.value,
                ClaimType.OPENING_HOURS_CANDIDATE.value,
                ClaimType.TICKET_PRICE_CANDIDATE.value,
            }:
                return EvidenceUsageRole(claim_support=True)
        if ct := _primary_claim_type(ev):
            if ct == ClaimType.PLACE_CANDIDATES.value:
                return EvidenceUsageRole(entity_anchor=True, context_only=True)
            if ct in {ClaimType.COORDINATES.value, ClaimType.POI_UID.value, ClaimType.RESOLVED_ADDRESS.value}:
                return EvidenceUsageRole(entity_anchor=True, context_only=True)
        if st == SourceType.MAP.value or "baidu" in src or "place_search" in src:
            return EvidenceUsageRole(entity_anchor=True, context_only=True)
        return EvidenceUsageRole(context_only=True)

    if st == SourceType.MAP.value:
        return EvidenceUsageRole(entity_anchor=True, context_only=claim_type not in {"nearby_food", "nearby_poi"})
    return EvidenceUsageRole(claim_support=True)


def _primary_claim_type(ev: Evidence) -> str | None:
    for claim in ev.claims or []:
        return claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
    return None


def is_entity_anchor_only(ev: Evidence, claim_type: str) -> bool:
    role = infer_evidence_usage_role(ev, claim_type)
    return role.entity_anchor and not role.claim_support
