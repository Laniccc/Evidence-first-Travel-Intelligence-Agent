from app.evidence import CitationChecker, ClaimDecision, TransientEvidence, evaluate_claims
from app.evidence.knowledge.models import FactType


def test_evidence_facade_exposes_only_the_bounded_rag_decision_surface():
    assert CitationChecker is not None
    assert ClaimDecision is not None
    assert TransientEvidence is not None
    assert evaluate_claims is not None
    assert FactType.TICKET_PRICE.value == "ticket_price"
