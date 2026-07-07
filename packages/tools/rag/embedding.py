"""Embedding service using bge-small-zh-v1.5 for Chinese text."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
_embedding_model: Any = None


def get_embedding_fn(model_name: str | None = None) -> Any:
    """Return a callable that encodes text to a 512-dim vector.

    Returns None if sentence-transformers is not installed.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model.encode

    mname = model_name or DEFAULT_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", mname)
        _embedding_model = SentenceTransformer(mname)
        return _embedding_model.encode
    except ImportError:
        logger.warning("sentence-transformers not installed — RAG disabled")
        return None
    except Exception as e:
        logger.warning("Embedding model load failed: %s", e)
        return None


def create_embedding(text: str, model_name: str | None = None) -> list[float] | None:
    """Encode a single text to a vector. Returns None on failure."""
    encode_fn = get_embedding_fn(model_name)
    if encode_fn is None:
        return None
    try:
        embedding = encode_fn(text)
        return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return None
