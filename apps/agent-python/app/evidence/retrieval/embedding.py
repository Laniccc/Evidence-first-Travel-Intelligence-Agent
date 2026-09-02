"""Embedding ports with an offline deterministic implementation."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable


class EmbeddingUnavailableError(RuntimeError):
    """Raised when a configured real embedding provider cannot be used."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    model_name: str
    dimension: int

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicHashEmbedding:
    """Feature-hashing embedder for repeatable offline tests, not semantic claims."""

    model_name = "deterministic-hash-v1"

    def __init__(self, dimension: int = 512) -> None:
        if dimension < 1:
            raise ValueError("embedding dimension must be positive")
        self.dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        features = self._features(text)
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    @staticmethod
    def _features(text: str) -> list[str]:
        normalized = " ".join(text.casefold().split())
        words = re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", normalized)
        compact = "".join(words)
        bigrams = [compact[index : index + 2] for index in range(max(0, len(compact) - 1))]
        return words + bigrams or ["<empty>"]


class FastEmbedEmbedding:
    """Lazy FastEmbed adapter used only by the explicit real-embedding profile."""

    def __init__(self, model_name: str, dimension: int) -> None:
        if dimension < 1:
            raise ValueError("embedding dimension must be positive")
        self.model_name = model_name
        self.dimension = dimension
        self._model = None

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = [vector.tolist() for vector in self._get_model().embed(texts)]
        except EmbeddingUnavailableError:
            raise
        except Exception as exc:
            raise EmbeddingUnavailableError(
                f"FastEmbed model '{self.model_name}' is unavailable"
            ) from exc
        for vector in vectors:
            if len(vector) != self.dimension:
                raise EmbeddingUnavailableError(
                    f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}"
                )
        return vectors

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        except Exception as exc:
            raise EmbeddingUnavailableError(
                f"FastEmbed model '{self.model_name}' is unavailable"
            ) from exc
        return self._model
