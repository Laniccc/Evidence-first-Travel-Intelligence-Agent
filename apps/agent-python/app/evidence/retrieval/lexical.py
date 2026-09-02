"""SQLite FTS5 lexical retrieval constrained to active document versions."""

from __future__ import annotations

import re

from app.evidence.knowledge.repository import KnowledgeRepository, _iso
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.fusion import ChannelHit


class SQLiteLexicalRetriever:
    MAX_LIMIT = 20

    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def retrieve(self, plan: RetrievalPlan, *, limit: int = 20) -> list[ChannelHit]:
        if not 1 <= limit <= self.MAX_LIMIT:
            raise ValueError(f"lexical limit must be between 1 and {self.MAX_LIMIT}")
        tokens = re.findall(r"[\w\u3400-\u9fff]+", plan.query_text.casefold())
        if not tokens:
            return []
        match_query = " OR ".join(f'"{token}"' for token in tokens)
        attraction_marks = ",".join("?" for _ in plan.attraction_ids)
        fact_types = [item.value for item in plan.fact_types]
        fact_clause = ""
        parameters: list = [match_query, *plan.attraction_ids]
        if fact_types:
            fact_marks = ",".join("?" for _ in fact_types)
            fact_clause = f" AND chunk.fact_type IN ({fact_marks})"
            parameters.extend(fact_types)
        cutoff = _iso(plan.as_of)
        parameters.extend((cutoff, cutoff, limit))
        sql = f"""
            SELECT
                chunk.chunk_id,
                chunk.version_id AS document_version_id,
                version.content_hash,
                bm25(fact_chunk_fts) AS rank
            FROM fact_chunk_fts
            JOIN fact_chunk AS chunk ON chunk.chunk_id = fact_chunk_fts.chunk_id
            JOIN document_version AS version ON version.version_id = chunk.version_id
            WHERE fact_chunk_fts MATCH ?
              AND chunk.attraction_id IN ({attraction_marks})
              {fact_clause}
              AND version.status = 'active'
              AND (version.valid_from IS NULL OR version.valid_from <= ?)
              AND (version.valid_to IS NULL OR version.valid_to > ?)
            ORDER BY rank ASC, chunk.chunk_id ASC
            LIMIT ?
        """
        with self.repository._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [
            ChannelHit(
                chunk_id=row["chunk_id"],
                score=1.0 / (1.0 + abs(float(row["rank"]))),
                document_version_id=row["document_version_id"],
                content_hash=row["content_hash"],
                payload={
                    "chunk_id": row["chunk_id"],
                    "document_version_id": row["document_version_id"],
                    "content_hash": row["content_hash"],
                },
            )
            for row in rows
        ]
