import pytest

from app.evidence.retrieval.embedding import DeterministicHashEmbedding
from app.evidence.retrieval.hybrid import HybridRetriever
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.replay import ReplayService
from tests.fakes.failing_retrievers import chunk, plan, report


@pytest.mark.asyncio
async def test_replay_from_evidence_evaluate_reuses_artifacts_without_retrieval(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError("retrieval dependency must not run during replay")

    monkeypatch.setattr(HybridRetriever, "retrieve", forbidden)
    monkeypatch.setattr(SQLiteLexicalRetriever, "retrieve", forbidden)
    monkeypatch.setattr(DeterministicHashEmbedding, "embed_query", forbidden)

    retrieval_plan = plan()
    retrieval_report = report(
        retrieval_plan, hits=[chunk("e-1", "故宫八点三十分开放")]
    )
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    store.start_run(
        run_id="original-run",
        query_id="query-1",
        session_id="session-1",
        query="故宫开放时间",
    )
    store.append_phase_event(
        run_id="original-run",
        state="retrieval_plan",
        status="succeeded",
        attempt=1,
        output={"retrieval_plans": [retrieval_plan.model_dump(mode="json")]},
    )
    store.append_phase_event(
        run_id="original-run",
        state="hybrid_retrieve",
        status="succeeded",
        attempt=1,
        output={"retrieval_reports": [retrieval_report.model_dump(mode="json")]},
    )

    # Complete an original run before requesting an artifact-only replay.
    from app.orchestration.state_contracts import StateContext
    from app.orchestration.states.evidence_evaluation import EvidenceEvaluationHandler
    from app.orchestration.states.answer_composition import GroundedCompositionHandler
    from app.orchestration.states.citation_guard import CitationGuardHandler
    from app.orchestration.states.delivery import DeliveryHandler
    context = StateContext(run_id="original-run", query_id="query-1", session_id="session-1", raw_query="query",
        artifacts={e.state: e.output for e in store.phase_events("original-run")})
    for state, handler in (("evidence_evaluate", EvidenceEvaluationHandler()), ("compose", GroundedCompositionHandler()),
                           ("citation_guard", CitationGuardHandler())):
        result = await handler.run(context)
        context.artifacts[state] = result.output
    original_response = await DeliveryHandler().build_response(context)
    store.save_response_snapshot(context, original_response)
    store.finish_run("original-run", status="succeeded", current_state="deliver")

    result = await ReplayService(store).replay(
        query_id="query-1", from_state="evidence_evaluate"
    )

    assert result.response.answer
    assert result.response.answer_claims[0]["evidence_ids"] == ["e-1"]
    assert result.run.replay_of_run_id == "original-run"
    assert result.run.run_id != "original-run"
