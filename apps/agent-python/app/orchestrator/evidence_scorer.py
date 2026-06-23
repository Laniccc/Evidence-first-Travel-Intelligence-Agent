"""Score evidence relevance and reliability for a claim (S7)."""

from __future__ import annotations

from dataclasses import dataclass

from app.orchestrator.claim_policy_registry import (
    GEO_ONLY_CLAIMS,
    REVIEW_EXPERIENCE_CLAIMS,
    SOURCE_RELIABILITY,
    ClaimPolicyView,
    source_type_key,
)
from app.orchestrator.claim_search_planner import is_search_miss_value
from app.schemas.evidence import Claim, ClaimType, Evidence, SourceType


@dataclass
class EvidenceScore:
    evidence_id: str
    claim_type: str
    source_name: str | None
    source_type: str | None
    claim_value: str
    total_score: float
    source_reliability: float
    claim_relevance: float
    claim_support: float
    freshness: float
    specificity: float
    tool_success: float
    corroboration_bonus: float = 0.0
    conflict_penalty: float = 0.0
    rank_reason: str = ""


class EvidenceScorer:
  def score_claim_evidence(
      self,
      policy: ClaimPolicyView,
      evidence: list,
      *,
      tool_traces: list | None = None,
  ) -> list[EvidenceScore]:
      rows: list[EvidenceScore] = []
      for ev in evidence:
          if not isinstance(ev, Evidence):
              continue
          for claim in ev.claims:
              if not self._is_relevant(policy, claim, ev):
                  continue
              value = str(claim.value)
              if is_search_miss_value(value):
                  continue
              rows.append(self._score_one(policy, ev, claim, tool_traces or []))
      return sorted(rows, key=lambda r: r.total_score, reverse=True)

  def _is_relevant(self, policy: ClaimPolicyView, claim: Claim, ev: Evidence) -> bool:
      ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
      if ct in policy.irrelevant_claim_types:
          return False
      if policy.claim_type == "ticket_price" and ct in {
          ClaimType.REVIEW_SUMMARY.value,
          ClaimType.REVIEW_ASPECT.value,
      }:
          return False
      if policy.claim_type in REVIEW_EXPERIENCE_CLAIMS:
          if ct in {ClaimType.TICKET_PRICE.value, ClaimType.OPENING_HOURS.value}:
              return False
          if ct in {
              ClaimType.REVIEW_SUMMARY.value,
              ClaimType.REVIEW_ASPECT.value,
              ClaimType.TRAVEL_ADVICE.value,
              ClaimType.TICKET_RELATED_MENTIONS.value,
          }:
              return True
          if policy.claim_type in policy.claim_aliases or ct in policy.claim_aliases:
              return True
          return "review" in ct or "suitability" in policy.claim_type
      if ct in GEO_ONLY_CLAIMS and policy.claim_family != "geo_fact":
          return False
      if ct in policy.claim_aliases or policy.claim_type in ct:
          return True
      if policy.claim_type in ct:
          return True
      if policy.policy_tier == "generic":
          return len(str(claim.value)) >= 3
      return False

  def _score_one(
      self,
      policy: ClaimPolicyView,
      ev: Evidence,
      claim: Claim,
      tool_traces: list,
  ) -> EvidenceScore:
      src_key = source_type_key(ev.source_type, ev.source_name)
      source_rel = SOURCE_RELIABILITY.get(src_key, 0.45)
      ct = claim.claim_type.value if hasattr(claim.claim_type, "value") else str(claim.claim_type)
      relevance = 0.9 if ct in policy.claim_aliases else 0.55
      if policy.claim_type == "ticket_price" and ct in {
          ClaimType.TICKET_PRICE_CANDIDATE.value,
          ClaimType.PRICE_CANDIDATE.value,
          ClaimType.TICKET_RELATED_MENTIONS.value,
      }:
          relevance = 0.65
      support = min(1.0, float(claim.confidence) * float(ev.confidence or 0.5) * 2)
      freshness = 0.8 if (ev.data_freshness and ev.data_freshness.value == "recent") else 0.55
      value = str(claim.value)
      specificity = 0.9 if any(ch.isdigit() for ch in value) or len(value) > 40 else 0.5
      tool_success = 1.0
      for trace in tool_traces:
          if getattr(trace, "evidence_ids", None) and ev.evidence_id in trace.evidence_ids:
              if trace.status != "ok":
                  tool_success = 0.4
      if ev.source_type == SourceType.MODEL_PRIOR and policy.requires_exact_fact:
          source_rel = min(source_rel, 0.25)
          relevance *= 0.3
      total = (
          source_rel * 0.30
          + relevance * 0.25
          + support * 0.20
          + freshness * 0.10
          + specificity * 0.10
          + tool_success * 0.05
      )
      return EvidenceScore(
          evidence_id=ev.evidence_id,
          claim_type=policy.claim_type,
          source_name=ev.source_name,
          source_type=ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
          claim_value=value,
          total_score=round(total, 4),
          source_reliability=source_rel,
          claim_relevance=relevance,
          claim_support=support,
          freshness=freshness,
          specificity=specificity,
          tool_success=tool_success,
          rank_reason=f"{src_key} rel={relevance:.2f}",
      )
