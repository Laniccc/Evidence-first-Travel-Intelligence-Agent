"""Small, fail-closed Qdrant boundary for attraction fact chunks."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.contracts.vector_index import VectorFilters, VectorHit, VectorPoint


class QdrantVectorIndex:
    MAX_SEARCH_LIMIT = 20

    def __init__(
        self,
        client: QdrantClient,
        *,
        collection: str,
        dimension: int,
    ) -> None:
        if dimension < 1:
            raise ValueError("vector dimension must be positive")
        self.client = client
        self.collection = collection
        self.dimension = dimension

    @staticmethod
    def point_id(chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"attraction-fact:{chunk_id}"))

    def recreate(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=models.VectorParams(
                size=self.dimension,
                distance=models.Distance.COSINE,
            ),
        )

    def upsert(self, points: Iterable[VectorPoint]) -> None:
        records: list[models.PointStruct] = []
        for point in points:
            if len(point.vector) != self.dimension:
                raise ValueError(
                    f"vector dimension mismatch: expected {self.dimension}, got {len(point.vector)}"
                )
            payload = point.model_dump(exclude={"vector"})
            records.append(
                models.PointStruct(
                    id=self.point_id(
                        f"{point.corpus_version}:{point.embedding_model}:{point.chunk_id}"
                    ),
                    vector=point.vector,
                    payload=payload,
                )
            )
        if records:
            self._assert_collection_dimension()
            self.client.upsert(
                collection_name=self.collection,
                points=records,
                wait=True,
            )

    def delete(
        self,
        chunk_ids: Iterable[str],
        *,
        corpus_version: str,
        embedding_model: str,
    ) -> None:
        ids = [
            self.point_id(f"{corpus_version}:{embedding_model}:{chunk_id}")
            for chunk_id in chunk_ids
        ]
        if ids:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.PointIdsList(points=ids),
                wait=True,
            )

    def search(
        self,
        vector: list[float],
        *,
        filters: VectorFilters,
        limit: int,
    ) -> list[VectorHit]:
        if not 1 <= limit <= self.MAX_SEARCH_LIMIT:
            raise ValueError(f"search limit must be between 1 and {self.MAX_SEARCH_LIMIT}")
        if len(vector) != self.dimension:
            raise ValueError(
                f"query vector dimension mismatch: expected {self.dimension}, got {len(vector)}"
            )
        self._assert_collection_dimension()
        response = self.client.query_points(
            collection_name=self.collection,
            query=vector,
            query_filter=self._filter(filters),
            limit=limit,
            with_payload=True,
        )
        return [
            VectorHit(
                chunk_id=str(point.payload["chunk_id"]),
                score=float(point.score),
                payload=dict(point.payload),
            )
            for point in response.points
        ]

    def count(self, filters: VectorFilters | None = None) -> int:
        self._assert_collection_dimension()
        result = self.client.count(
            collection_name=self.collection,
            count_filter=self._filter(filters) if filters else None,
            exact=True,
        )
        return int(result.count)

    def health(self) -> bool:
        self._assert_collection_dimension()
        return True

    def verify_generation(self, chunks, *, corpus_version, embedding_model):
        self._assert_collection_dimension()
        for start in range(0, len(chunks), 128):
            batch = chunks[start:start + 128]
            ids = [self.point_id(f"{corpus_version}:{embedding_model}:{c.chunk_id}") for c in batch]
            points = {str(p.id): p.payload for p in self.client.retrieve(
                self.collection, ids=ids, with_payload=True, with_vectors=False)}
            for chunk, point_id in zip(batch, ids, strict=True):
                payload = points.get(point_id, {})
                expected = {"chunk_id": chunk.chunk_id, "document_version_id": chunk.document_version_id,
                    "content_hash": chunk.content_hash, "attraction_id": chunk.attraction_id,
                    "fact_type": chunk.fact_type.value, "corpus_version": corpus_version,
                    "embedding_model": embedding_model, "source_id": chunk.source_id}
                if any(payload.get(key) != value for key, value in expected.items()):
                    return False
        return True

    def _assert_collection_dimension(self) -> None:
        if not self.client.collection_exists(self.collection):
            raise ValueError(f"Qdrant collection does not exist: {self.collection}")
        info = self.client.get_collection(self.collection)
        vectors = info.config.params.vectors
        actual = getattr(vectors, "size", None)
        if actual != self.dimension:
            raise ValueError(
                f"Qdrant collection dimension mismatch: expected {self.dimension}, got {actual}"
            )

    @staticmethod
    def _filter(filters: VectorFilters) -> models.Filter:
        must: list[models.FieldCondition] = [
            models.FieldCondition(
                key="attraction_id",
                match=models.MatchAny(any=filters.attraction_ids),
            )
        ]
        if filters.fact_types:
            must.append(
                models.FieldCondition(
                    key="fact_type",
                    match=models.MatchAny(any=filters.fact_types),
                )
            )
        if filters.corpus_version:
            must.append(
                models.FieldCondition(
                    key="corpus_version",
                    match=models.MatchValue(value=filters.corpus_version),
                )
            )
        if filters.embedding_model:
            must.append(
                models.FieldCondition(
                    key="embedding_model",
                    match=models.MatchValue(value=filters.embedding_model),
                )
            )
        return models.Filter(must=must)
