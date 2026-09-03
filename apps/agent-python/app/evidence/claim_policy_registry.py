"""Claim policies restricted to the managed attraction knowledge corpus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evidence.claim_family_registry import CLAIM_TYPE_ALIASES, CLAIM_TYPE_TO_FAMILY
from app.evidence.evidence_model import SourceType
from app.evidence.evidence_policy import EvidencePolicy


GEO_ONLY_CLAIMS = frozenset({"place_candidates", "coordinates", "poi_uid", "address"})
REVIEW_EXPERIENCE_CLAIMS: frozenset[str] = frozenset()
SOURCE_RELIABILITY = {
    "official": 0.95,
    "knowledge_base": 0.90,
    "public_web": 0.50,
    "search_result": 0.45,
    "model_prior": 0.25,
    "fallback": 0.20,
}


@dataclass
class ClaimPolicyView:
    claim_type: str
    claim_family: str
    claim_description: str | None
    priority: str
    requires_exact_fact: bool
    requires_live_data: bool
    model_prior_allowed: bool
    estimation_allowed: bool
    preferred_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    allowed_source_types: list[str] = field(default_factory=list)
    coverage_rule: str = ""
    missing_behavior: str = "answer_with_limitation"
    policy_tier: str = "generic"
    claim_aliases: frozenset[str] = field(default_factory=frozenset)
    irrelevant_claim_types: frozenset[str] = field(default_factory=frozenset)
    known_in_registry: bool = False


def enrich_claim_requirement(claim: Any) -> Any:
    family = claim.claim_family or CLAIM_TYPE_TO_FAMILY.get(claim.claim_type, "managed_fact")
    description = claim.claim_description or claim.claim_type.replace("_", " ")
    return claim.model_copy(update={"claim_family": family, "claim_description": description})


def resolve_policy(claim: Any) -> ClaimPolicyView:
    claim = enrich_claim_requirement(claim)
    evidence_policy = EvidencePolicy.get(claim.claim_type)
    known = claim.claim_type in CLAIM_TYPE_TO_FAMILY
    return ClaimPolicyView(
        claim_type=claim.claim_type,
        claim_family=claim.claim_family or "managed_fact",
        claim_description=claim.claim_description,
        priority=claim.priority,
        requires_exact_fact=claim.requires_exact_fact or evidence_policy.requires_exact_fact,
        requires_live_data=claim.requires_live_data or evidence_policy.requires_live_data,
        model_prior_allowed=claim.model_prior_allowed and evidence_policy.model_prior_allowed,
        estimation_allowed=claim.estimation_allowed,
        preferred_tools=list(claim.preferred_tools) or ["hybrid_retrieval"],
        forbidden_tools=list(claim.forbidden_tools),
        allowed_source_types=list(claim.allowed_source_types) or list(evidence_policy.preferred_source_types),
        coverage_rule=claim.coverage_rule or "managed fact requires source provenance",
        missing_behavior=claim.missing_behavior,
        policy_tier="known" if known else "generic",
        claim_aliases=CLAIM_TYPE_ALIASES.get(claim.claim_type, frozenset({claim.claim_type})),
        irrelevant_claim_types=GEO_ONLY_CLAIMS,
        known_in_registry=known,
    )


class GenericOpenClaimPolicy:
    @staticmethod
    def from_requirement(claim: Any) -> ClaimPolicyView:
        return resolve_policy(claim)


def source_type_key(source_type, source_name: str | None) -> str:
    value = source_type.value if isinstance(source_type, SourceType) else str(source_type or "").lower()
    if value == "official":
        return "official"
    if value == "model_prior":
        return "model_prior"
    if "search" in (source_name or "").lower():
        return "search_result"
    return value if value in SOURCE_RELIABILITY else "public_web"
