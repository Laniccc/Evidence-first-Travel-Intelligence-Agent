import pytest

from app.composition.answer_claim import AnswerClaim
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.answer_composition import GroundedCompositionHandler
from tests.fakes.failing_retrievers import chunk, plan, report


def context():
    retrieval_report = report(
        plan(), hits=[chunk("e-1", "故宫八点三十分开放")]
    )
    return StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="故宫开放时间",
        artifacts={
            "hybrid_retrieve": {
                "retrieval_reports": [retrieval_report.model_dump(mode="json")]
            },
            "evidence_evaluate": {
                "claim_decisions": [
                    {
                        "claim_id": "sub-1:opening_hours",
                        "claim_type": "opening_hours",
                        "required": True,
                        "coverage_quality": "strong",
                        "adoption": "adopt",
                        "adopted_evidence_ids": ["e-1"],
                        "adopted_value": "故宫八点三十分开放",
                        "attraction_id": "forbidden-city",
                        "subtask_id": "sub-1",
                    }
                ],
                "common_fact_types": [],
            },
        },
    )


@pytest.mark.asyncio
async def test_composition_outputs_claims_and_evidence_index():
    result = await GroundedCompositionHandler().run(context())

    assert result.next_state is AgentState.CITATION_GUARD
    claim = AnswerClaim.model_validate(result.output["answer_claims"][0])
    assert claim.evidence_ids == ["e-1"]
    assert result.output["evidence_index"]["e-1"]["source_url"].startswith("https://")


class InvalidComposer:
    def __init__(self):
        self.repairs = []

    async def compose_claims(self, bundle, *, repair):
        self.repairs.append(repair)
        return {"invalid": True}


@pytest.mark.asyncio
async def test_composition_uses_single_attempt_then_deterministic_fallback():
    composer = InvalidComposer()
    result = await GroundedCompositionHandler(composer=composer).run(context())

    assert composer.repairs == [False]
    assert result.output["composition_mode"] == "deterministic_fallback"
    assert result.output["answer_claims"][0]["text"] == "故宫八点三十分开放"
