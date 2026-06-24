"""S7 deterministic evidence evaluation orchestrator."""

from __future__ import annotations

from app.config import get_settings
from app.orchestrator.claim_adoption_policy import ClaimAdoptionPolicy
from app.orchestrator.claim_policy_registry import enrich_claim_requirement, resolve_policy
from app.orchestrator.evidence_conflict_resolver import EvidenceConflictResolver
from app.orchestrator.evidence_coverage_checker import EvidenceCoverageChecker
from app.orchestrator.evidence_gap_planner import EvidenceGapPlanner
from app.orchestrator.evidence_scorer import EvidenceScorer
from app.schemas.coverage_report import CoverageReport
from app.schemas.evidence_decision_report import (
    EvidenceDecisionReport,
    RejectedEvidence,
    SourceRanking,
)
from app.schemas.response_contract import ResponseContract
from app.schemas.user_query import TravelAgentState


class EvidenceEvaluator:
    def __init__(self) -> None:
        self.scorer = EvidenceScorer()
        self.conflicts = EvidenceConflictResolver()
        self.adoption = ClaimAdoptionPolicy()
        self.gap_planner = EvidenceGapPlanner()
        self.coverage_checker = EvidenceCoverageChecker()

    def evaluate(self, state: TravelAgentState, *, target_label: str) -> EvidenceDecisionReport:
        contract = state.response_contract or ResponseContract()
        claims = [enrich_claim_requirement(c) for c in contract.claim_requirements]
        if not claims:
            claims = [enrich_claim_requirement(c) for c in self._default_claims(state)]

        settings = get_settings()
        gap_round = state.gap_loop_state.gap_round if state.gap_loop_state else 0
        max_rounds = (
            state.gap_loop_state.max_gap_rounds
            if state.gap_loop_state
            else settings.evidence_max_gap_rounds
        )
        seen_signatures = set(state.gap_loop_state.gap_signatures if state.gap_loop_state else [])

        decisions = []
        rankings: list[SourceRanking] = []
        all_conflicts = []
        all_rejected: list[RejectedEvidence] = []
        gap_requests = []

        fact_decomposition = list((state.structured_result or {}).get("fact_decomposition") or [])

        for claim in claims:
            policy = resolve_policy(claim)
            scores = self.scorer.score_claim_evidence(policy, state.evidence, tool_traces=state.tool_traces)
            for s in scores[:5]:
                rankings.append(
                    SourceRanking(
                        claim_type=policy.claim_type,
                        evidence_id=s.evidence_id,
                        source_name=s.source_name,
                        source_type=s.source_type,
                        score=s.total_score,
                        rank_reason=s.rank_reason,
                    )
                )
            claim_conflicts, preferred = self.conflicts.resolve(
                policy.claim_type, scores, evidence=state.evidence
            )
            decision, rejected = self.adoption.decide(
                policy,
                scores,
                claim_conflicts,
                preferred_id=preferred,
                evidence=state.evidence,
                fact_decomposition=fact_decomposition,
            )
            decisions.append(decision)
            all_conflicts.extend(claim_conflicts)
            all_rejected.extend(rejected)

            if decision.coverage_quality in {"none", "weak"} and claim.priority in {"required", "important"}:
                gap = self.gap_planner.plan_gaps(
                    state,
                    claim,
                    policy,
                    decision,
                    gap_round=gap_round,
                    max_gap_rounds=max_rounds,
                )
                if gap and gap.gap_signature not in seen_signatures:
                    gap_requests.append(gap)

        overall = 0.0
        if decisions:
            overall = sum(d.confidence for d in decisions) / len(decisions)

        report = EvidenceDecisionReport(
            claim_decisions=decisions,
            source_rankings=rankings,
            conflicts=all_conflicts,
            rejected_evidence=all_rejected,
            evidence_gap_requests=gap_requests,
            overall_confidence=round(overall, 3),
            summary=f"evaluated {len(decisions)} claims for {target_label}",
        )
        state.coverage_report = self._build_coverage_report(contract, decisions)
        return report

    def _build_coverage_report(self, contract: ResponseContract, decisions) -> CoverageReport:
        from app.schemas.coverage_report import CoverageItem

        items = []
        for claim, decision in zip(contract.claim_requirements, decisions):
            items.append(
                CoverageItem(
                    claim_type=decision.claim_type,
                    covered=decision.coverage_quality in {"partial", "strong"},
                    evidence_ids=decision.adopted_evidence_ids,
                    missing_reason=None if decision.coverage_quality != "none" else decision.reason,
                    coverage_quality=decision.coverage_quality,
                    can_answer=decision.adoption not in {"refuse_to_guess", "ask_clarification"},
                    missing_behavior=claim.missing_behavior,
                )
            )
        required = [i for i, c in zip(items, contract.claim_requirements) if c.priority == "required"]
        all_required = all(i.covered for i in required) if required else True
        return CoverageReport(
            items=items,
            all_required_covered=all_required,
            can_finish_evidence_planning=True,
            answer_should_include_limitations=any(
                d.adoption in {"adopt_with_limitation", "candidate_only", "refuse_to_guess"} for d in decisions
            ),
            summary="; ".join(f"{d.claim_type}:{d.coverage_quality}" for d in decisions),
        )

    @staticmethod
    def _default_claims(state: TravelAgentState):
        from app.schemas.response_contract import ClaimRequirement

        needs = []
        if state.semantic_frame:
            needs = list(state.semantic_frame.information_needs or [])
        if not needs:
            needs = ["general_travel_advice"]
        return [ClaimRequirement(claim_type=n, priority="important") for n in needs[:3]]


def evaluate_evidence(state: TravelAgentState, *, target_label: str) -> EvidenceDecisionReport:
    return EvidenceEvaluator().evaluate(state, target_label=target_label)
