from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.embedding import EmbeddingUnavailableError
from app.evidence.retrieval.fusion import ChannelHit
from app.evidence.retrieval.hybrid import HybridRetriever, QdrantDenseRetriever
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever


class StaticRetriever:
    def __init__(self, hits):
        self.hits = hits

    def retrieve(self, plan, *, limit):
        return list(self.hits)


class FailingRetriever:
    def __init__(self, message="timeout"):
        self.message = message

    def retrieve(self, plan, *, limit):
        raise TimeoutError(self.message)


@pytest.fixture
def seeded_repo(tmp_path):
    repo = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    for source_id, content, fact_type in (
        ("reservation", "预约 入馆 需要提前实名预约", FactType.RESERVATION),
        ("reservation-2", "预约 入馆 需要携带有效证件", FactType.RESERVATION),
        ("hours", "开放 时间 每日九点开始", FactType.OPENING_HOURS),
    ):
        result = repo.ingest(
            KnowledgeDocument(
                source_id=source_id,
                attraction=Attraction(
                    attraction_id="forbidden-city",
                    name="故宫博物院",
                ),
                url=f"https://example.test/{source_id}",
                title=source_id,
                source_type=SourceType.OFFICIAL,
                content=content,
                chunks=[FactChunkDraft(fact_type=fact_type, content=content)],
            )
        )
        repo.publish(result.version_id)
    generation = repo.start_index_generation("corpus-1", "fake-v1")
    repo.complete_index_generation(generation.generation_id, indexed_chunk_count=3)
    return repo


def make_plan(*, top_k=3, subtask_id="fact-1"):
    return RetrievalPlan(
        task_type="fact_query",
        query_text="预约 入馆",
        attraction_ids=["forbidden-city"],
        fact_types=[FactType.RESERVATION],
        as_of=datetime.now(UTC),
        top_k=top_k,
        subtask_id=subtask_id,
    )


def dense_hit(chunk, *, content_hash=None):
    return ChannelHit(
        chunk_id=chunk.chunk_id,
        score=0.9,
        payload={
            "chunk_id": chunk.chunk_id,
            "document_version_id": chunk.document_version_id,
            "content_hash": content_hash or chunk.content_hash,
        },
    )


def reservation_chunk(repo):
    return next(
        chunk
        for chunk in repo.list_active_chunks(datetime.now(UTC))
        if chunk.fact_type is FactType.RESERVATION
    )


def test_qdrant_timeout_recovers_with_lexical_only(seeded_repo):
    retriever = HybridRetriever(
        repository=seeded_repo,
        lexical=SQLiteLexicalRetriever(seeded_repo),
        dense=FailingRetriever("qdrant timeout"),
    )

    report = retriever.retrieve(make_plan())

    assert report.degradation == "lexical_only"
    assert report.dense_attempt.failure_code == "timeout"
    assert report.final_hits
    assert report.final_hits[0].retrieval_channels == ["lexical"]


def test_fts_failure_recovers_with_dense_only(seeded_repo):
    chunk = reservation_chunk(seeded_repo)
    retriever = HybridRetriever(
        repository=seeded_repo,
        lexical=FailingRetriever("fts unavailable"),
        dense=StaticRetriever([dense_hit(chunk)]),
    )

    report = retriever.retrieve(make_plan())

    assert report.degradation == "dense_only"
    assert report.lexical_attempt.failure_code == "timeout"
    assert [hit.chunk_id for hit in report.final_hits] == [chunk.chunk_id]


def test_both_channels_failed_returns_a_complete_empty_report(seeded_repo):
    report = HybridRetriever(
        repository=seeded_repo,
        lexical=FailingRetriever("fts unavailable"),
        dense=FailingRetriever("qdrant unavailable"),
    ).retrieve(make_plan())

    assert report.degradation == "all_failed"
    assert report.final_hits == []
    assert report.lexical_attempt.status == "failed"
    assert report.dense_attempt.status == "failed"
    assert report.latency_breakdown.total_ms >= 0


def test_both_channels_empty_is_audited_as_no_results(seeded_repo):
    report = HybridRetriever(
        repository=seeded_repo,
        lexical=StaticRetriever([]),
        dense=StaticRetriever([]),
    ).retrieve(make_plan())

    assert report.degradation == "no_results"
    assert report.lexical_attempt.status == "empty"
    assert report.dense_attempt.status == "empty"
    assert report.coverage_hints == ["no_active_evidence"]


def test_stale_dense_point_is_rejected_by_sqlite_hash(seeded_repo):
    chunk = reservation_chunk(seeded_repo)
    report = HybridRetriever(
        repository=seeded_repo,
        lexical=StaticRetriever([]),
        dense=StaticRetriever([dense_hit(chunk, content_hash="stale-hash")]),
    ).retrieve(make_plan())

    assert report.final_hits == []
    assert report.post_filter_rejections[0].reason == "hash_mismatch"


def test_superseded_dense_point_is_rejected(seeded_repo):
    old_chunk = reservation_chunk(seeded_repo)
    update = seeded_repo.ingest(
        KnowledgeDocument(
            source_id=old_chunk.source_id,
            attraction=Attraction(attraction_id="forbidden-city", name="故宫博物院"),
            url=old_chunk.source_url,
            title=old_chunk.source_title,
            source_type=SourceType.OFFICIAL,
            content="预约 入馆 更新后的实名预约规定",
            chunks=[
                FactChunkDraft(
                    fact_type=FactType.RESERVATION,
                    content="预约 入馆 更新后的实名预约规定",
                )
            ],
        )
    )
    seeded_repo.publish(update.version_id)

    report = HybridRetriever(
        repository=seeded_repo,
        lexical=StaticRetriever([]),
        dense=StaticRetriever([dense_hit(old_chunk)]),
    ).retrieve(make_plan())

    assert report.final_hits == []
    assert report.post_filter_rejections[0].reason == "superseded_version"


@pytest.mark.parametrize(
    ("publish", "valid_to", "expected_reason"),
    [
        (False, None, "pending_version"),
        (True, datetime.now(UTC) - timedelta(minutes=1), "expired_version"),
    ],
)
def test_non_active_dense_points_are_rejected(
    seeded_repo,
    publish,
    valid_to,
    expected_reason,
):
    result = seeded_repo.ingest(
        KnowledgeDocument(
            source_id=f"non-active-{expected_reason}",
            attraction=Attraction(attraction_id="forbidden-city", name="故宫博物院"),
            url=f"https://example.test/{expected_reason}",
            title=expected_reason,
            source_type=SourceType.OFFICIAL,
            content="预约 入馆 非活动版本",
            valid_to=valid_to,
            chunks=[
                FactChunkDraft(
                    fact_type=FactType.RESERVATION,
                    content="预约 入馆 非活动版本",
                )
            ],
        )
    )
    if publish:
        seeded_repo.publish(result.version_id)
        seeded_repo.expire_due()
    with seeded_repo._connect() as connection:
        chunk_id = connection.execute(
            "SELECT chunk_id FROM fact_chunk WHERE version_id = ?",
            (result.version_id,),
        ).fetchone()["chunk_id"]
    chunk = seeded_repo.get_chunk(chunk_id)

    report = HybridRetriever(
        repository=seeded_repo,
        lexical=StaticRetriever([]),
        dense=StaticRetriever([dense_hit(chunk)]),
    ).retrieve(make_plan())

    assert report.final_hits == []
    assert report.post_filter_rejections[0].reason == expected_reason


def test_hybrid_top_k_and_subtask_id_are_isolated(seeded_repo):
    chunk = reservation_chunk(seeded_repo)
    retriever = HybridRetriever(
        repository=seeded_repo,
        lexical=SQLiteLexicalRetriever(seeded_repo),
        dense=StaticRetriever([dense_hit(chunk)]),
    )

    first = retriever.retrieve(make_plan(top_k=1, subtask_id="comparison:a"))
    second = retriever.retrieve(make_plan(top_k=1, subtask_id="comparison:b"))

    assert len(first.final_hits) == 1
    assert first.subtask_id == "comparison:a"
    assert second.subtask_id == "comparison:b"
    assert first is not second


def test_dense_retrieval_fails_closed_when_embedding_model_drifted(seeded_repo):
    class WrongEmbedder:
        model_name = "different-model"
        dimension = 8

        def embed_query(self, text):
            raise AssertionError("must fail before embedding")

    with pytest.raises(EmbeddingUnavailableError, match="does not match"):
        QdrantDenseRetriever(
            seeded_repo,
            vector_index=object(),
            embedder=WrongEmbedder(),
        ).retrieve(make_plan())
