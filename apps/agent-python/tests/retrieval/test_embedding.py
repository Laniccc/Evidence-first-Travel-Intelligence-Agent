import math

import pytest

from app.evidence.retrieval.embedding import DeterministicHashEmbedding
from app.config import Settings


def test_deterministic_embedder_is_stable_and_normalized():
    embedder = DeterministicHashEmbedding(dimension=16)

    first = embedder.embed_query("故宫是否需要预约")
    second = embedder.embed_query("故宫是否需要预约")

    assert first == second
    assert len(first) == 16
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_deterministic_embedder_keeps_document_order():
    embedder = DeterministicHashEmbedding(dimension=8)

    vectors = embedder.embed_documents(["开放时间", "预约须知"])

    assert vectors == [
        embedder.embed_query("开放时间"),
        embedder.embed_query("预约须知"),
    ]
    assert all(math.isclose(sum(value * value for value in vector), 1.0) for vector in vectors)


def test_deterministic_embedder_rejects_invalid_dimension():
    with pytest.raises(ValueError, match="dimension"):
        DeterministicHashEmbedding(dimension=0)


def test_empty_qdrant_api_key_is_normalized_to_none():
    assert Settings(qdrant_api_key="   ").qdrant_api_key is None
