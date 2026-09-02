import pytest

from app.orchestration.state_contracts import StateContext
from app.orchestration.states.delivery import DeliveryHandler


@pytest.mark.asyncio
async def test_delivery_builds_typed_response_with_claim_and_citation_audit():
    state = StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="query",
        artifacts={
            "citation_guard": {
                "answer": "故宫八点三十分开放。",
                "supported_claims": [
                    {
                        "claim_id": "c-1",
                        "text": "故宫八点三十分开放。",
                        "claim_type": "opening_hours",
                        "hard_fact": True,
                        "evidence_ids": ["e-1"],
                    }
                ],
                "citation_report": {"passed": True, "decisions": []},
                "evidence_index": {"e-1": {"source_url": "https://example.test"}},
            },
            "hybrid_retrieve": {"retrieval_reports": [{"subtask_id": "sub-1"}]},
        },
    )

    response = await DeliveryHandler().build_response(state)

    assert response.session_id == "session-1"
    assert response.query_id == "query-1"
    assert response.answer_claims[0]["claim_id"] == "c-1"
    assert response.citation_report["passed"] is True
    assert response.retrieval_reports[0]["subtask_id"] == "sub-1"
