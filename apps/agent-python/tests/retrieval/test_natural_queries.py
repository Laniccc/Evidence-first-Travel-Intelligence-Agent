from datetime import UTC, datetime, timedelta

import pytest

from app.evidence.knowledge.models import Attraction, FactChunkDraft, FactType, KnowledgeDocument, SourceType
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.fusion import reciprocal_rank_fusion
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.evidence.retrieval.reranker import filter_and_rerank
from app.planning.retrieval_query_builder import RetrievalQueryBuilder


NOW = datetime(2026, 9, 4, tzinfo=UTC)


def add(repo, source_id, content, *, valid_from=None, valid_to=None):
    result = repo.ingest(KnowledgeDocument(
        source_id=source_id, attraction=Attraction(attraction_id="palace", name="故宫博物院"),
        url="https://example.test/" + source_id, title="开放时间", source_type=SourceType.OFFICIAL,
        content=content, fetched_at=NOW, valid_from=valid_from, valid_to=valid_to,
        chunks=[FactChunkDraft(fact_type=FactType.OPENING_HOURS, content=content)],
    ))
    repo.publish(result.version_id)
    return result


def plan(**changes):
    values = dict(task_type="fact_query", query_text="故宫几点开门", raw_query="故宫几点开门",
                  attraction_ids=["palace"], fact_types=[FactType.OPENING_HOURS],
                  as_of=NOW, subtask_id="q:1:palace", lexical_query=RetrievalQueryBuilder()
                  .from_entity_and_fact_types("故宫博物院", [FactType.OPENING_HOURS], aliases=["故宫"]))
    values.update(changes)
    return RetrievalPlan(**values)


@pytest.mark.parametrize("content", ["开放时间：08:30—17:00", "开放时间为08:30至17:00"])
def test_unspaced_chinese_question_hits_without_changing_dense_query(tmp_path, content):
    repo = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    expected = add(repo, "hours", content)
    request = plan()
    hits = SQLiteLexicalRetriever(repo).retrieve(request)
    assert [h.document_version_id for h in hits] == [expected.version_id]
    assert request.query_text == "故宫几点开门"
    assert "OR" not in request.lexical_query


def test_query_expansion_is_bounded_and_no_user_generated_fts_operators():
    query = RetrievalQueryBuilder().from_entity_and_fact_types(
        '故宫" OR *', [FactType.OPENING_HOURS], aliases=["故宫"] * 1000)
    assert len(query.split()) <= 32
    assert "*" not in query and '"' not in query and " OR " not in query


def test_requested_future_or_history_requires_explicit_coverage_for_both_channels(tmp_path):
    repo = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    add(repo, "snapshot", "开放时间：08:30—17:00")
    add(repo, "future", "开放时间：09:00—17:00",
        valid_from=NOW + timedelta(days=1), valid_to=NOW + timedelta(days=3))
    requested = plan(as_of=NOW + timedelta(days=2), require_explicit_temporal_coverage=True)
    lexical_hits = SQLiteLexicalRetriever(repo).retrieve(requested)
    assert len(lexical_hits) == 1
    # Dense deliberately supplies the current unbounded snapshot too.
    all_hits = SQLiteLexicalRetriever(repo).retrieve(plan())
    candidates = reciprocal_rank_fusion(lexical=lexical_hits, dense=all_hits)
    accepted, rejected = filter_and_rerank(repo, plan=requested, candidates=candidates, corpus_version="test")
    assert len(accepted) == 1 and accepted[0].content == "开放时间：09:00—17:00"
    assert any(r.reason == "temporal_coverage_missing" for r in rejected)
    historical = plan(as_of=NOW - timedelta(days=30), require_explicit_temporal_coverage=True)
    assert SQLiteLexicalRetriever(repo).retrieve(historical) == []
    accepted, _ = filter_and_rerank(repo, plan=historical, candidates=candidates, corpus_version="test")
    assert accepted == []


def test_current_transient_snapshot_cannot_answer_a_different_requested_time():
    from app.evidence.claim_decision import TransientEvidence, evaluate_claims

    live = TransientEvidence(
        evidence_id="live", attraction_id="palace", fact_type="opening_hours",
        content="08:30开放", source_name="地图", source_url="https://example.test/live",
        retrieved_at=NOW,
    )
    for offset in (-30, 30):
        requested = plan(as_of=NOW + timedelta(days=offset), require_explicit_temporal_coverage=True)
        outcome = evaluate_claims(plans=[requested], reports=[], transient_evidence=[live])
        assert outcome.claim_decisions[0].adoption == "refuse_to_guess"
