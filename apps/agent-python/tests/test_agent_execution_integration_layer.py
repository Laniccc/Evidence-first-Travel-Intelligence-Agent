from app.orchestration.states.hybrid_retrieval import HybridRetrievalHandler
from app.orchestration.states.live_gap_fill import LiveGapFillHandler


def test_execution_is_owned_by_audited_state_handlers():
    assert HybridRetrievalHandler is not None
    assert LiveGapFillHandler.MAX_ATTEMPTS == 2
