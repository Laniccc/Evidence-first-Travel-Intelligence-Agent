"""Version-aware lexical and dense evidence retrieval."""

from app.evidence.retrieval.contracts import VectorFilters, VectorHit, VectorPoint
from app.evidence.retrieval.embedding import (
    DeterministicHashEmbedding,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    FastEmbedEmbedding,
)

__all__ = [
    "DeterministicHashEmbedding",
    "EmbeddingProvider",
    "EmbeddingUnavailableError",
    "FastEmbedEmbedding",
    "VectorFilters",
    "VectorHit",
    "VectorPoint",
]
