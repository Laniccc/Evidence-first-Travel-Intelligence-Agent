"""Compatibility strategy projection for the bounded state-chain routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.planning.s5_information_domain import InformationDomain
from app.understanding.intent_profile import AnswerStyle, EvidenceSensitivity, IntentProfile, PrimaryIntent


S7PolicyName = Literal["hard_fact_strict", "aligned_dimension_comparison", "open_claim_advisory", "clarification_decision"]
RetrievalMode = Literal["minimal_probe", "strict_fact_lookup", "multi_place_parallel", "mixed_advisory"]


class IntentToolTiers(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    fallback: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class IntentStrategy(BaseModel):
    primary_intent: PrimaryIntent
    evidence_sensitivity: EvidenceSensitivity
    retrieval_mode: RetrievalMode = "mixed_advisory"
    s7_policy: S7PolicyName = "open_claim_advisory"
    domain_priority: list[InformationDomain] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    tool_tiers: IntentToolTiers = Field(default_factory=IntentToolTiers)
    preferred_subagents: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    skip_s5: bool = False
    partial_review_ok: bool = False
    single_platform_partial: bool = False
    refuse_asymmetric_comparison: bool = False
    stale_evidence_downgrade: bool = False
    forbid_model_prior_for_live: bool = False
    answer_style: AnswerStyle = AnswerStyle.ADVISORY
    compose_mode: str = "advisory"
    composition_policy_style: str = "advisory"
    state_chain_hint: str = "understand → route → retrieve → evaluate → compose → cite"


def resolve_intent_strategy(profile: IntentProfile | None) -> IntentStrategy | None:
    if profile is None:
        return None
    hard_fact = profile.evidence_sensitivity in {EvidenceSensitivity.HARD_FACT, EvidenceSensitivity.LIVE_REQUIRED}
    comparison = profile.primary_intent == PrimaryIntent.COMPARISON
    clarification = profile.primary_intent == PrimaryIntent.CLARIFICATION
    return IntentStrategy(
        primary_intent=profile.primary_intent,
        evidence_sensitivity=profile.evidence_sensitivity,
        retrieval_mode="multi_place_parallel" if comparison else ("minimal_probe" if clarification else "strict_fact_lookup"),
        s7_policy="aligned_dimension_comparison" if comparison else ("clarification_decision" if clarification else ("hard_fact_strict" if hard_fact else "open_claim_advisory")),
        preferred_tools=["hybrid_retrieval", "official_page_reader_mcp"],
        skip_s5=clarification,
        refuse_asymmetric_comparison=comparison,
        stale_evidence_downgrade=True,
        forbid_model_prior_for_live=True,
        answer_style=AnswerStyle.DIRECT_FACT if hard_fact else profile.answer_style,
        compose_mode="comparison" if comparison else ("clarification" if clarification else "advisory"),
        composition_policy_style="comparison" if comparison else "advisory",
    )
