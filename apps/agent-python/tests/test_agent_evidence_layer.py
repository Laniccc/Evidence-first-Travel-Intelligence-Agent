from app.evidence import (
    CitationChecker,
    ClaimRelevanceFilterAgent,
    EvidenceAggregator,
    EvidenceConflictAnalyzerAgent,
    EvidenceConflictResolver,
    EvidenceContradictionDecomposerAgent,
    EvidenceCoverageChecker,
    EvidenceCurationPlannerAgent,
    EvidenceEvaluator,
    EvidencePolicyGuard,
    ReviewAspectMiningAgent,
    RuleReviewAspectExtractor,
    VerifierAgent,
    filter_subagent_evidence,
)
from app.evidence.evidence_model import Claim, ClaimType, DataFreshness, Evidence, SourceType
from app.evidence.source_quality import score_source_quality


def test_evidence_model_is_owned_by_final_evidence_module():
    evidence = Evidence(
        source_name="Official source",
        source_type=SourceType.OFFICIAL,
        source_url="https://example.test",
        country="Japan",
        data_freshness=DataFreshness.LIVE,
        confidence=0.9,
        claims=[Claim(claim_type=ClaimType.OPENING_HOURS, value="09:00-17:00")],
    )

    assert evidence.__class__.__module__ == "app.evidence.evidence_model"
    assert evidence.claims[0].claim_type is ClaimType.OPENING_HOURS


def test_source_quality_scores_official_live_evidence_higher_than_stale_social_evidence():
    official = Evidence(
        source_name="Official source",
        source_type=SourceType.OFFICIAL,
        source_url="https://example.test",
        country="Japan",
        data_freshness=DataFreshness.LIVE,
        confidence=0.9,
    )
    social = Evidence(
        source_name="Social post",
        source_type=SourceType.SOCIAL,
        country="Japan",
        data_freshness=DataFreshness.STALE,
        confidence=0.9,
    )

    official_score = score_source_quality(official)
    social_score = score_source_quality(social)

    assert official_score.score > social_score.score
    assert "source_type:official" in official_score.reasons
    assert "missing_source_url" in social_score.reasons


def test_evidence_facades_export_current_capabilities():
    assert EvidenceAggregator is not None
    assert ClaimRelevanceFilterAgent is not None
    assert EvidenceConflictAnalyzerAgent is not None
    assert EvidenceConflictResolver is not None
    assert EvidenceContradictionDecomposerAgent is not None
    assert EvidenceCoverageChecker is not None
    assert EvidenceCurationPlannerAgent is not None
    assert EvidenceEvaluator is not None
    assert EvidencePolicyGuard is not None
    assert CitationChecker is not None
    assert ReviewAspectMiningAgent is not None
    assert RuleReviewAspectExtractor is not None
    assert VerifierAgent is not None
    assert filter_subagent_evidence is not None
