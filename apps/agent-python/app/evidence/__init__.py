"""Evidence product capability layer."""

from importlib import import_module
from typing import Any


_EXPORTS = {
    "ClaimFamilySpec": ("app.evidence.claim_family_registry", "ClaimFamilySpec"),
    "ClaimPolicyView": ("app.evidence.claim_policy_registry", "ClaimPolicyView"),
    "CitationChecker": ("app.evidence.citation_checker", "CitationChecker"),
    "ClaimRelevanceFilterAgent": (
        "app.evidence.claim_relevance_filter_agent",
        "ClaimRelevanceFilterAgent",
    ),
    "Claim": ("app.evidence.evidence_model", "Claim"),
    "ClaimType": ("app.evidence.evidence_model", "ClaimType"),
    "DataFreshness": ("app.evidence.evidence_model", "DataFreshness"),
    "Evidence": ("app.evidence.evidence_model", "Evidence"),
    "EvidenceAggregator": ("app.evidence.evidence_aggregator", "EvidenceAggregator"),
    "EvidenceConflictResolver": ("app.evidence.conflict_resolver", "EvidenceConflictResolver"),
    "EvidenceConflictAnalyzerAgent": (
        "app.evidence.evidence_conflict_analyzer_agent",
        "EvidenceConflictAnalyzerAgent",
    ),
    "EvidenceContradictionDecomposerAgent": (
        "app.evidence.evidence_contradiction_decomposer_agent",
        "EvidenceContradictionDecomposerAgent",
    ),
    "EvidenceCurationPlannerAgent": (
        "app.evidence.evidence_curation_planner_agent",
        "EvidenceCurationPlannerAgent",
    ),
    "EvidenceCoverageChecker": ("app.evidence.coverage_checker", "EvidenceCoverageChecker"),
    "EvidenceEvaluator": ("app.evidence.evidence_evaluator", "EvidenceEvaluator"),
    "EvidencePolicyGuard": ("app.evidence.policy_guard", "EvidencePolicyGuard"),
    "EvidencePolicy": ("app.evidence.evidence_policy", "EvidencePolicy"),
    "ReviewAspectMiningAgent": ("app.evidence.review_mining_agent", "ReviewAspectMiningAgent"),
    "AspectNormalizer": ("app.evidence.review_aspect_normalizer", "AspectNormalizer"),
    "LLMReviewAspectExtractor": (
        "app.evidence.review_llm_extractor",
        "LLMReviewAspectExtractor",
    ),
    "PersonaImplicationGenerator": (
        "app.evidence.review_persona_generator",
        "PersonaImplicationGenerator",
    ),
    "RuleReviewAspectExtractor": (
        "app.evidence.review_rule_extractor",
        "RuleReviewAspectExtractor",
    ),
    "VerifierAgent": ("app.evidence.review_mining_agent", "VerifierAgent"),
    "ClaimPolicy": ("app.evidence.evidence_policy", "ClaimPolicy"),
    "CitationPolicy": ("app.evidence.citation_policy", "CitationPolicy"),
    "LicenseScope": ("app.evidence.evidence_model", "LicenseScope"),
    "SourceQualityResult": ("app.evidence.source_quality", "SourceQualityResult"),
    "SourcePriorityPolicy": ("app.evidence.source_priority_policy", "SourcePriorityPolicy"),
    "SourceType": ("app.evidence.evidence_model", "SourceType"),
    "apply_evidence_brief": ("app.evidence.evidence_brief", "apply_evidence_brief"),
    "apply_intent_s7_policy": ("app.evidence.intent_s7_policy", "apply_intent_s7_policy"),
    "build_evidence_brief": ("app.evidence.evidence_brief", "build_evidence_brief"),
    "build_evidence_brief_from_report": (
        "app.evidence.evidence_brief",
        "build_evidence_brief_from_report",
    ),
    "evaluate_evidence": ("app.evidence.evidence_evaluator", "evaluate_evidence"),
    "filter_subagent_evidence": ("app.evidence.subagent_gate", "filter_subagent_evidence"),
    "resolve_claim_policy": ("app.evidence.claim_policy_registry", "resolve_policy"),
    "score_source_quality": ("app.evidence.source_quality", "score_source_quality"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
