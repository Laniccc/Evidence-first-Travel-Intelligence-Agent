"""Real Qdrant boundary smoke test, enabled only in the dedicated CI job."""

import os
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.evidence.retrieval.contracts import VectorFilters, VectorPoint
from app.integrations.qdrant.vector_index import QdrantVectorIndex


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_QDRANT_INTEGRATION") != "1",
    reason="requires the dedicated Qdrant service job",
)


def test_remote_qdrant_round_trip_with_metadata_filter():
    collection = f"ci-attraction-facts-{uuid4().hex}"
    client = QdrantClient(
        url=os.getenv("QDRANT_URL", "http://127.0.0.1:6333"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )
    index = QdrantVectorIndex(client, collection=collection, dimension=4)
    try:
        index.recreate()
        index.upsert(
            [
                VectorPoint(
                    chunk_id="ci-hours",
                    vector=[1.0, 0.0, 0.0, 0.0],
                    attraction_id="forbidden-city",
                    fact_type="opening_hours",
                    document_version_id="ci-version",
                    content_hash="ci-hash",
                    corpus_version="ci-corpus",
                    embedding_model="ci-fake",
                    source_id="ci-source",
                    source_authority=1.0,
                )
            ]
        )
        hits = index.search(
            [1.0, 0.0, 0.0, 0.0],
            filters=VectorFilters(
                attraction_ids=["forbidden-city"],
                fact_types=["opening_hours"],
                corpus_version="ci-corpus",
                embedding_model="ci-fake",
            ),
            limit=3,
        )
        assert [hit.chunk_id for hit in hits] == ["ci-hours"]
    finally:
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()
