from uuid import UUID

import pytest
from qdrant_client import QdrantClient

from app.evidence.retrieval.contracts import VectorFilters, VectorPoint
from app.integrations.qdrant.vector_index import QdrantVectorIndex


def point(
    chunk_id: str,
    vector: list[float],
    *,
    attraction: str = "forbidden-city",
    fact: str = "reservation",
    corpus_version: str = "corpus-1",
) -> VectorPoint:
    return VectorPoint(
        chunk_id=chunk_id,
        vector=vector,
        attraction_id=attraction,
        fact_type=fact,
        document_version_id="version-1",
        content_hash=f"hash-{chunk_id}",
        corpus_version=corpus_version,
    )


@pytest.fixture
def client():
    instance = QdrantClient(":memory:")
    yield instance
    instance.close()


def test_qdrant_index_filters_and_round_trips_payload(client):
    index = QdrantVectorIndex(client, collection="attraction-facts-test", dimension=4)
    index.recreate()
    index.upsert(
        [
            point("chunk-1", [1, 0, 0, 0]),
            point("chunk-2", [1, 0, 0, 0], attraction="summer-palace"),
            point("chunk-3", [1, 0, 0, 0], fact="opening_hours"),
        ]
    )

    hits = index.search(
        [1, 0, 0, 0],
        filters=VectorFilters(
            attraction_ids=["forbidden-city"],
            fact_types=["reservation"],
            corpus_version="corpus-1",
        ),
        limit=3,
    )

    assert [hit.chunk_id for hit in hits] == ["chunk-1"]
    assert hits[0].payload["document_version_id"] == "version-1"
    assert hits[0].payload["content_hash"] == "hash-chunk-1"
    assert index.count() == 3
    assert index.health() is True


def test_arbitrary_chunk_id_maps_to_stable_uuid():
    first = QdrantVectorIndex.point_id("任意 chunk/id")
    second = QdrantVectorIndex.point_id("任意 chunk/id")

    assert first == second
    assert str(UUID(first)) == first


def test_collection_dimension_mismatch_fails_closed(client):
    QdrantVectorIndex(client, collection="dimension-test", dimension=4).recreate()

    with pytest.raises(ValueError, match="dimension"):
        QdrantVectorIndex(client, collection="dimension-test", dimension=8).health()


def test_search_limit_is_bounded(client):
    index = QdrantVectorIndex(client, collection="limit-test", dimension=4)
    index.recreate()

    with pytest.raises(ValueError, match="20"):
        index.search(
            [1, 0, 0, 0],
            filters=VectorFilters(attraction_ids=["forbidden-city"]),
            limit=21,
        )
