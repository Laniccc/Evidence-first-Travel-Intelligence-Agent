"""Blue/green synchronization from authoritative SQLite chunks to Qdrant."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock

_locks = {}
_locks_guard = RLock()

from app.evidence.knowledge.models import IndexSyncResult
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import VectorFilters, VectorPoint
from app.evidence.retrieval.embedding import EmbeddingProvider


class IndexSyncError(RuntimeError):
    """A failed generation that has already been persisted for audit."""

    def __init__(self, generation_id: str, message: str) -> None:
        super().__init__(message)
        self.generation_id = generation_id


class IndexSynchronizer:
    def __init__(self, repository: KnowledgeRepository, *, vector_index, embedder: EmbeddingProvider) -> None:
        self.repository = repository
        self.vector_index = vector_index
        self.embedder = embedder

    def rebuild(self, *, corpus_version: str) -> IndexSyncResult:
        with _locks_guard:
            lock = _locks.setdefault(str(self.repository.db_path.resolve()), RLock())
        # Same-process rebuilds are serialized; production also uses the dense lane.
        with lock:
            return self._rebuild(corpus_version=corpus_version)

    def _rebuild(self, *, corpus_version: str) -> IndexSyncResult:
        chunks = self.repository.list_active_chunks(datetime.now(UTC))
        expected_hash = self.repository.corpus_digest(chunks)
        active = self.repository.active_index_generation()
        if (
            active is not None
            and active.corpus_version == corpus_version
            and active.embedding_model == self.embedder.model_name
        ):
            try:
                valid = self._generation_valid(chunks, corpus_version)
            except Exception:
                valid = False
            if valid and self.repository.compute_corpus_version() == expected_hash:
                return IndexSyncResult(**active.model_dump(), reused=True,
                    cleanup_failure_code=active.failure_code)

        generation = self.repository.start_index_generation(
            corpus_version,
            self.embedder.model_name,
        )
        try:
            self._ensure_collection()
            vectors = self.embedder.embed_documents([chunk.content for chunk in chunks])
            if len(vectors) != len(chunks):
                raise ValueError(
                    f"embedding count mismatch: expected {len(chunks)}, got {len(vectors)}"
                )
            points = [
                VectorPoint(
                    chunk_id=chunk.chunk_id,
                    vector=vector,
                    attraction_id=chunk.attraction_id,
                    fact_type=chunk.fact_type.value,
                    document_version_id=chunk.document_version_id,
                    content_hash=chunk.content_hash,
                    corpus_version=corpus_version,
                    embedding_model=self.embedder.model_name,
                    source_id=chunk.source_id,
                    source_authority=chunk.source_authority,
                    valid_from=chunk.valid_from,
                    valid_to=chunk.valid_to,
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            self.vector_index.upsert(points)
            for chunk in chunks:
                self.repository.mark_chunk_indexed(
                    generation.generation_id,
                    chunk_id=chunk.chunk_id,
                    qdrant_point_id=self.vector_index.point_id(
                        f"{corpus_version}:{self.embedder.model_name}:{chunk.chunk_id}"
                    ),
                    content_hash=chunk.content_hash,
                )
            if not self._generation_valid(chunks, corpus_version):
                raise ValueError("Qdrant consistency mismatch")
            completed = self.repository.complete_index_generation(
                generation.generation_id, indexed_chunk_count=len(chunks),
                expected_corpus_hash=expected_hash)
        except Exception as exc:
            failure_code = self._failure_code(exc)
            for chunk in chunks:
                if chunk.chunk_id not in self.repository.list_generation_chunk_ids(
                    generation.generation_id
                ):
                    self.repository.mark_chunk_failed(
                        generation.generation_id,
                        chunk_id=chunk.chunk_id,
                        content_hash=chunk.content_hash,
                        failure_code=failure_code,
                    )
            self.repository.fail_index_generation(
                generation.generation_id,
                failure_code=failure_code,
                failed_chunk_count=len(chunks),
            )
            raise IndexSyncError(generation.generation_id, str(exc)) from exc

        deleted_count = 0
        cleanup_failure_code = None
        if active is not None and (active.corpus_version, active.embedding_model) != (corpus_version, self.embedder.model_name):
            old_chunk_ids = self.repository.list_generation_chunk_ids(active.generation_id)
            try:
                self.vector_index.delete(
                    old_chunk_ids,
                    corpus_version=active.corpus_version,
                    embedding_model=active.embedding_model,
                )
                deleted_count = self.repository.mark_generation_chunks_deleted(
                    active.generation_id
                )
            except Exception as exc:
                cleanup_failure_code = self._failure_code(exc)
        self.repository.record_generation_cleanup(
            completed.generation_id,
            deleted_chunk_count=deleted_count,
            failure_code=cleanup_failure_code,
        )
        completed = self.repository.get_index_generation(completed.generation_id)
        return IndexSyncResult(
            **completed.model_dump(),
            cleanup_failure_code=cleanup_failure_code,
        )

    def _ensure_collection(self) -> None:
        try:
            self.vector_index.health()
        except ValueError as exc:
            if "does not exist" not in str(exc):
                raise
            self.vector_index.recreate()

    def _generation_count(self, chunks, corpus_version: str) -> int:
        if not chunks:
            return 0
        return self.vector_index.count(
            VectorFilters(
                attraction_ids=list(dict.fromkeys(chunk.attraction_id for chunk in chunks)),
                corpus_version=corpus_version,
                embedding_model=self.embedder.model_name,
            )
        )

    def _generation_valid(self, chunks, corpus_version):
        if self._generation_count(chunks, corpus_version) != len(chunks):
            return False
        # Concrete Qdrant boundary verifies every expected ID, version and hash.
        verifier = getattr(self.vector_index, "verify_generation", None)
        return verifier(chunks, corpus_version=corpus_version, embedding_model=self.embedder.model_name) if verifier else True

    @staticmethod
    def _failure_code(exc: Exception) -> str:
        if isinstance(exc, ValueError) and str(exc) == "corpus_drift":
            return "corpus_drift"
        name = type(exc).__name__.removesuffix("Error")
        words = []
        current = ""
        for char in name:
            if char.isupper() and current:
                words.append(current.lower())
                current = char
            else:
                current += char
        if current:
            words.append(current.lower())
        return "_".join(words) or "index_sync_failure"
