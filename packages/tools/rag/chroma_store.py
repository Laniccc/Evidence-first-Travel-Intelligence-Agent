"""ChromaDB vector store wrapper for research evidence."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class ChromaEvidenceStore:
    """ChromaDB-backed vector store for research evidence.

    Stores evidence embeddings + metadata for semantic retrieval.
    Zero-config if chromadb is installed; data persists to disk.
    """

    def __init__(self, persist_path: str = "./data/chroma", collection_name: str = "research_evidence"):
        self.persist_path = persist_path
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    @property
    def client(self):
        if self._client is None:
            try:
                import chromadb
                os.makedirs(self.persist_path, exist_ok=True)
                self._client = chromadb.PersistentClient(path=self.persist_path)
                logger.info("ChromaDB initialized at %s", self.persist_path)
            except ImportError:
                logger.warning("chromadb not installed — RAG disabled")
                return None
            except Exception as e:
                logger.warning("ChromaDB init failed: %s — RAG disabled", e)
                return None
        return self._client

    @property
    def collection(self):
        if self._collection is None and self.client is not None:
            try:
                self._collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                logger.warning("ChromaDB collection error: %s", e)
                return None
        return self._collection

    def add(self, embeddings, documents, metadatas, ids) -> None:
        """Add evidence to the vector store."""
        if self.collection is None:
            return
        try:
            self.collection.add(
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
        except Exception as e:
            logger.warning("ChromaDB add failed: %s", e)

    def query(self, query_embedding, n_results: int = 10, where: dict | None = None) -> list[dict[str, Any]]:
        """Semantic search for similar evidence."""
        if self.collection is None:
            return []
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            return [
                {
                    "id": ids[0],
                    "document": docs[0],
                    "metadata": meta[0] if meta else {},
                    "distance": dist[0] if dist else 0,
                }
                for ids, docs, meta, dist in zip(
                    results.get("ids", [[]])[0],
                    results.get("documents", [[]])[0],
                    results.get("metadatas", [[]])[0],
                    results.get("distances", [[]])[0],
                )
            ]
        except Exception as e:
            logger.warning("ChromaDB query failed: %s", e)
            return []

    def count(self) -> int:
        """Return total stored documents."""
        if self.collection is None:
            return 0
        try:
            return self.collection.count()
        except Exception:
            return 0
