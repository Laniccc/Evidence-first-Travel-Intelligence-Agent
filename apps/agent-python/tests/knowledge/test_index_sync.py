from __future__ import annotations

from datetime import UTC, datetime

import pytest
from qdrant_client import QdrantClient

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.embedding import DeterministicHashEmbedding
from app.evidence.retrieval.index_sync import IndexSyncError, IndexSynchronizer
from app.evidence.retrieval.contracts import VectorFilters
from app.integrations.qdrant.vector_index import QdrantVectorIndex


class FakeVectorIndex:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.fail_upsert = fail_upsert
        self.points = {}
        self.upsert_calls = 0
        self.deleted = []

    @staticmethod
    def point_id(value: str) -> str:
        return f"point:{value}"

    def health(self) -> bool:
        return True

    def recreate(self) -> None:
        self.points.clear()

    def upsert(self, points) -> None:
        self.upsert_calls += 1
        if self.fail_upsert:
            raise TimeoutError("qdrant timeout")
        for point in points:
            self.points[(point.corpus_version, point.embedding_model, point.chunk_id)] = point

    def count(self, filters=None) -> int:
        if filters is None or filters.corpus_version is None:
            return len(self.points)
        return sum(
            corpus_version == filters.corpus_version
            and (filters.embedding_model is None or embedding_model == filters.embedding_model)
            and point.attraction_id in filters.attraction_ids
            for (corpus_version, embedding_model, _), point in self.points.items()
        )

    def delete(self, chunk_ids, *, corpus_version: str, embedding_model: str) -> None:
        for chunk_id in chunk_ids:
            self.points.pop((corpus_version, embedding_model, chunk_id), None)
            self.deleted.append((corpus_version, embedding_model, chunk_id))


@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepository(tmp_path / "knowledge.sqlite3")


def document(content: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        source_id="source-forbidden-city-hours",
        attraction=Attraction(
            attraction_id="forbidden-city",
            name="故宫博物院",
            city="北京",
            country="中国",
        ),
        url="https://www.dpm.org.cn/visit/hours",
        title="故宫参观时间",
        source_type=SourceType.OFFICIAL,
        content=content,
        chunks=[FactChunkDraft(fact_type=FactType.OPENING_HOURS, content=content)],
    )


def publish(repo: KnowledgeRepository, content: str) -> str:
    result = repo.ingest(document(content))
    repo.publish(result.version_id)
    return result.version_id


def test_failed_rebuild_never_replaces_active_generation(repo):
    publish(repo, "开放时间 09:00-17:00")
    healthy = FakeVectorIndex()
    IndexSynchronizer(
        repo,
        vector_index=healthy,
        embedder=DeterministicHashEmbedding(dimension=8),
    ).rebuild(corpus_version="corpus-1")
    active_before = repo.active_index_generation()

    with pytest.raises(IndexSyncError, match="qdrant timeout"):
        IndexSynchronizer(
            repo,
            vector_index=FakeVectorIndex(fail_upsert=True),
            embedder=DeterministicHashEmbedding(dimension=8),
        ).rebuild(corpus_version="corpus-2")

    assert repo.active_index_generation().generation_id == active_before.generation_id


def test_rebuild_is_idempotent_for_same_corpus_and_model(repo):
    publish(repo, "开放时间 09:00-17:00")
    vector_index = FakeVectorIndex()
    synchronizer = IndexSynchronizer(
        repo,
        vector_index=vector_index,
        embedder=DeterministicHashEmbedding(dimension=8),
    )

    first = synchronizer.rebuild(corpus_version="corpus-1")
    second = synchronizer.rebuild(corpus_version="corpus-1")

    assert first.generation_id == second.generation_id
    assert second.reused is True
    assert vector_index.upsert_calls == 1


def test_successful_rebuild_removes_superseded_generation_points(repo):
    publish(repo, "开放时间 09:00-17:00")
    vector_index = FakeVectorIndex()
    synchronizer = IndexSynchronizer(
        repo,
        vector_index=vector_index,
        embedder=DeterministicHashEmbedding(dimension=8),
    )
    synchronizer.rebuild(corpus_version="corpus-1")
    old_generation_id = repo.active_index_generation().generation_id
    old_chunk_id = repo.list_generation_chunk_ids(old_generation_id)[0]

    publish(repo, "开放时间 08:30-17:00")
    result = synchronizer.rebuild(corpus_version="corpus-2")

    assert result.status == "active"
    assert ("corpus-1", "deterministic-hash-v1", old_chunk_id) in vector_index.deleted
    assert repo.list_generation_chunk_ids(old_generation_id) == []
    assert repo.list_generation_chunk_ids(result.generation_id)
    assert all(key[0] == "corpus-2" for key in vector_index.points)


def test_rebuild_works_with_qdrant_local_mode(repo):
    publish(repo, "开放时间 09:00-17:00")
    client = QdrantClient(":memory:")
    index = QdrantVectorIndex(client, collection="sync-test", dimension=8)
    try:
        result = IndexSynchronizer(
            repo,
            vector_index=index,
            embedder=DeterministicHashEmbedding(dimension=8),
        ).rebuild(corpus_version="corpus-local")

        assert result.indexed_chunk_count == 1
        assert index.count(
            VectorFilters(
                attraction_ids=["forbidden-city"],
                corpus_version="corpus-local",
                embedding_model="deterministic-hash-v1",
            )
        ) == 1
    finally:
        client.close()
