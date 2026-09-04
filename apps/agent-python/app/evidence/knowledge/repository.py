"""SQLite repository for attraction knowledge lifecycle state."""

from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.evidence.knowledge.migrations import migrate

from app.evidence.knowledge.models import (
    Attraction,
    DocumentVersion,
    IngestResult,
    IndexGeneration,
    IndexGenerationStatus,
    IndexableChunk,
    KnowledgeDocument,
    SOURCE_AUTHORITY,
    SourceDocumentRecord,
    SourceType,
    VersionStatus,
)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class KnowledgeRepository:
    def __init__(self, db_path: str | Path, *, clock=None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path = Path(__file__).with_name("schema.sql")
        with self._connect() as connection:
            connection.executescript(schema_path.read_text(encoding="utf-8"))
        migrate(self.db_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ingest(self, document: KnowledgeDocument) -> IngestResult:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._ingest(connection, document)

    def _ingest(self, connection, document: KnowledgeDocument) -> IngestResult:
        now = _iso(datetime.now(UTC))
        source = connection.execute("SELECT attraction_id FROM source_document WHERE source_id=?",
                                    (document.source_id,)).fetchone()
        if source and source["attraction_id"] != document.attraction.attraction_id:
            raise ValueError("source_binding_mismatch")
        connection.execute(
            """
            INSERT INTO attraction(
                attraction_id, name, aliases_json, city, country, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(attraction_id) DO UPDATE SET
                name = excluded.name,
                aliases_json = CASE
                    WHEN excluded.aliases_json = '[]' THEN attraction.aliases_json
                    ELSE excluded.aliases_json
                END,
                city = COALESCE(excluded.city, attraction.city),
                country = COALESCE(excluded.country, attraction.country),
                updated_at = excluded.updated_at
            """,
            (
                document.attraction.attraction_id,
                document.attraction.name,
                json.dumps(document.attraction.aliases, ensure_ascii=False),
                document.attraction.city,
                document.attraction.country,
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO source_document(
                source_id, attraction_id, url, title, source_type,
                authority_score, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                source_type = excluded.source_type,
                authority_score = excluded.authority_score,
                updated_at = excluded.updated_at
            """,
            (
                document.source_id,
                document.attraction.attraction_id,
                document.url,
                document.title,
                document.source_type.value,
                SOURCE_AUTHORITY[document.source_type],
                now,
                now,
            ),
        )
        existing = connection.execute(
            """
            SELECT version_id, status FROM document_version
            WHERE source_id = ? AND content_hash = ?
            """,
            (document.source_id, document.content_hash),
        ).fetchone()
        if existing:
            return IngestResult(
                source_id=document.source_id,
                version_id=existing["version_id"],
                content_hash=document.content_hash,
                status=VersionStatus(existing["status"]),
                created=False,
            )

        version_id = f"ver-{uuid4()}"
        active = connection.execute(
            "SELECT version_id FROM document_version WHERE source_id = ? AND status = 'active'",
            (document.source_id,),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO document_version(
                version_id, source_id, content_hash, content, status, fetched_at,
                valid_from, valid_to, supersedes_version_id, hash_version, payload_hash,
                source_url, source_title, source_type, source_authority
             ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, 2, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                document.source_id,
                document.content_hash,
                document.content,
                _iso(document.fetched_at),
                _iso(document.valid_from),
                _iso(document.valid_to),
                active["version_id"] if active else None,
                document.payload_hash, document.url, document.title,
                document.source_type.value, SOURCE_AUTHORITY[document.source_type],
            ),
        )
        for ordinal, chunk in enumerate(document.chunks):
            chunk_id = chunk.chunk_id or f"{version_id}:chunk:{ordinal}"
            if connection.execute("SELECT 1 FROM fact_chunk WHERE chunk_id=?", (chunk_id,)).fetchone():
                chunk_id = f"{version_id}:chunk:{ordinal}"
            connection.execute(
                """
                INSERT INTO fact_chunk(
                    chunk_id, version_id, attraction_id, fact_type, content, locator, language
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    version_id,
                    document.attraction.attraction_id,
                    chunk.fact_type.value,
                    chunk.content,
                    chunk.locator,
                    chunk.language,
                ),
            )
        return IngestResult(
            source_id=document.source_id,
            version_id=version_id,
            content_hash=document.content_hash,
            status=VersionStatus.PENDING,
            created=True,
        )

    def publish(self, version_id: str) -> DocumentVersion:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._publish(connection, version_id)
        return self.get_version(version_id)

    def _publish(self, connection, version_id):
        row = connection.execute("SELECT * FROM document_version WHERE version_id=?", (version_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown document version: {version_id}")
        if row["status"] == "active":
            return
        if row["status"] != "pending":
            raise ValueError(f"Only a pending version can be published, got {row['status']}")
        now = _iso(self._clock())
        if row["valid_to"] and row["valid_to"] <= now:
            raise ValueError("An expired version cannot be published")
        active = connection.execute("SELECT version_id FROM document_version WHERE source_id=? AND status='active'",
                                    (row["source_id"],)).fetchone()
        connection.execute("UPDATE document_version SET status='superseded' WHERE source_id=? AND status='active'",
                           (row["source_id"],))
        connection.execute("""UPDATE document_version SET status='active', published_at=?,
                           supersedes_version_id=?, rejection_reason=NULL WHERE version_id=? AND status='pending'""",
                           (now, active["version_id"] if active else None, version_id))

    def reject(self, version_id: str, *, reason: str) -> DocumentVersion:
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE document_version
                SET status = 'rejected', rejection_reason = ?
                WHERE version_id = ? AND status = 'pending'
                """,
                (reason, version_id),
            ).rowcount
            if not changed:
                raise ValueError("Unknown or active version cannot be rejected")
        return self.get_version(version_id)

    def expire_due(self, now: datetime | None = None) -> int:
        cutoff = _iso(now or datetime.now(UTC))
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE document_version
                SET status = 'expired'
                WHERE status = 'active' AND valid_to IS NOT NULL AND valid_to <= ?
                """,
                (cutoff,),
            ).rowcount

    def get_version(self, version_id: str) -> DocumentVersion:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM document_version WHERE version_id = ?",
                (version_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown document version: {version_id}")
        return self._version_from_row(row)

    def active_versions(self, attraction_id: str) -> list[DocumentVersion]:
        now = _iso(datetime.now(UTC))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT version.*
                FROM document_version AS version
                JOIN source_document AS source ON source.source_id = version.source_id
                WHERE source.attraction_id = ?
                  AND version.status = 'active'
                  AND (version.valid_to IS NULL OR version.valid_to > ?)
                ORDER BY source.source_id
                """,
                (attraction_id, now),
            ).fetchall()
        return [self._version_from_row(row) for row in rows]

    def count_versions(self, source_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM document_version WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return int(row["count"])

    def get_source(self, source_id: str) -> SourceDocumentRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_document WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown source document: {source_id}")
        return SourceDocumentRecord(
            source_id=row["source_id"],
            attraction_id=row["attraction_id"],
            url=row["url"],
            title=row["title"],
            source_type=SourceType(row["source_type"]),
            authority_score=row["authority_score"],
        )

    def list_active_chunks(self, as_of: datetime) -> list[IndexableChunk]:
        with self._connect() as connection:
            return self._active_chunks(connection, as_of)

    def _active_chunks(self, connection, as_of):
        cutoff = _iso(as_of)
        rows = connection.execute(
            """
            SELECT
                chunk.chunk_id,
                chunk.version_id AS document_version_id,
                chunk.attraction_id,
                chunk.fact_type,
                chunk.content,
                chunk.locator,
                chunk.language,
                version.content_hash,
                version.valid_from,
                version.valid_to,
                version.published_at,
                version.status AS version_status,
                source.source_id,
                version.source_url AS source_url,
                version.source_title AS source_title,
                version.source_type,
                version.source_authority AS source_authority
            FROM fact_chunk AS chunk
            JOIN document_version AS version ON version.version_id = chunk.version_id
            JOIN source_document AS source ON source.source_id = version.source_id
            WHERE version.status = 'active'
              AND (version.valid_from IS NULL OR version.valid_from <= ?)
              AND (version.valid_to IS NULL OR version.valid_to > ?)
            ORDER BY chunk.chunk_id
            """,
            (cutoff, cutoff),
        ).fetchall()
        return [self._indexable_chunk_from_row(row) for row in rows]

    def compute_corpus_version(self, as_of: datetime | None = None) -> str:
        chunks = self.list_active_chunks(as_of or datetime.now(UTC))
        return self.corpus_digest(chunks)

    @staticmethod
    def corpus_digest(chunks):
        digest_input = "\n".join(
            ":".join(
                (
                    chunk.source_id,
                    chunk.content_hash,
                    chunk.fact_type.value,
                    hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
                )
            )
            for chunk in chunks
        )
        return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]

    def get_chunk(self, chunk_id: str) -> IndexableChunk | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    chunk.chunk_id,
                    chunk.version_id AS document_version_id,
                    chunk.attraction_id,
                    chunk.fact_type,
                    chunk.content,
                    chunk.locator,
                    chunk.language,
                    version.content_hash,
                    version.valid_from,
                    version.valid_to,
                    version.published_at,
                    version.status AS version_status,
                    source.source_id,
                    version.source_url AS source_url,
                    version.source_title AS source_title,
                    version.source_type,
                    version.source_authority AS source_authority
                FROM fact_chunk AS chunk
                JOIN document_version AS version ON version.version_id = chunk.version_id
                JOIN source_document AS source ON source.source_id = version.source_id
                WHERE chunk.chunk_id = ?
                """,
                (chunk_id,),
            ).fetchone()
        return self._indexable_chunk_from_row(row) if row else None

    def start_index_generation(
        self,
        corpus_version: str,
        embedding_model: str,
    ) -> IndexGeneration:
        generation_id = f"idx-{uuid4()}"
        now = _iso(datetime.now(UTC))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO index_generation(
                    generation_id, corpus_version, embedding_model, status, started_at
                ) VALUES (?, ?, ?, 'building', ?)
                """,
                (generation_id, corpus_version, embedding_model, now),
            )
        return self.get_index_generation(generation_id)

    def mark_chunk_indexed(
        self,
        generation_id: str,
        *,
        chunk_id: str,
        qdrant_point_id: str,
        content_hash: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chunk_index_state(
                    generation_id, chunk_id, qdrant_point_id, content_hash,
                    status, last_attempt_at, failure_code
                ) VALUES (?, ?, ?, ?, 'indexed', ?, NULL)
                ON CONFLICT(generation_id, chunk_id) DO UPDATE SET
                    qdrant_point_id = excluded.qdrant_point_id,
                    content_hash = excluded.content_hash,
                    status = 'indexed',
                    last_attempt_at = excluded.last_attempt_at,
                    failure_code = NULL
                """,
                (
                    generation_id,
                    chunk_id,
                    qdrant_point_id,
                    content_hash,
                    _iso(datetime.now(UTC)),
                ),
            )

    def mark_chunk_failed(
        self,
        generation_id: str,
        *,
        chunk_id: str,
        content_hash: str,
        failure_code: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO chunk_index_state(
                    generation_id, chunk_id, content_hash, status,
                    last_attempt_at, failure_code
                ) VALUES (?, ?, ?, 'failed', ?, ?)
                ON CONFLICT(generation_id, chunk_id) DO UPDATE SET
                    status = 'failed',
                    last_attempt_at = excluded.last_attempt_at,
                    failure_code = excluded.failure_code
                """,
                (
                    generation_id,
                    chunk_id,
                    content_hash,
                    _iso(datetime.now(UTC)),
                    failure_code,
                ),
            )

    def complete_index_generation(
        self,
        generation_id: str,
        *,
        indexed_chunk_count: int,
        failed_chunk_count: int = 0,
        deleted_chunk_count: int = 0,
        expected_corpus_hash: str | None = None,
    ) -> IndexGeneration:
        now = _iso(datetime.now(UTC))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if expected_corpus_hash is not None and self.corpus_digest(self._active_chunks(connection, datetime.now(UTC))) != expected_corpus_hash:
                raise ValueError("corpus_drift")
            target = connection.execute(
                "SELECT status FROM index_generation WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if target is None:
                raise KeyError(f"Unknown index generation: {generation_id}")
            if target["status"] not in {
                IndexGenerationStatus.PENDING.value,
                IndexGenerationStatus.BUILDING.value,
            }:
                raise ValueError("Only a pending or building generation can be activated")
            connection.execute(
                """
                UPDATE index_generation
                SET status = 'superseded', completed_at = COALESCE(completed_at, ?)
                WHERE status = 'active' AND generation_id <> ?
                """,
                (now, generation_id),
            )
            connection.execute(
                """
                UPDATE index_generation
                SET status = 'active', completed_at = ?, indexed_chunk_count = ?,
                    failed_chunk_count = ?, deleted_chunk_count = ?, failure_code = NULL
                WHERE generation_id = ?
                """,
                (
                    now,
                    indexed_chunk_count,
                    failed_chunk_count,
                    deleted_chunk_count,
                    generation_id,
                ),
            )
        return self.get_index_generation(generation_id)

    def fail_index_generation(
        self,
        generation_id: str,
        *,
        failure_code: str,
        failed_chunk_count: int = 0,
    ) -> IndexGeneration:
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE index_generation
                SET status = 'failed', completed_at = ?, failure_code = ?,
                    failed_chunk_count = ?
                WHERE generation_id = ? AND status IN ('pending', 'building')
                """,
                (
                    _iso(datetime.now(UTC)),
                    failure_code,
                    failed_chunk_count,
                    generation_id,
                ),
            ).rowcount
            if not changed:
                raise ValueError("Only a pending or building generation can fail")
        return self.get_index_generation(generation_id)

    def record_generation_cleanup(
        self,
        generation_id: str,
        *,
        deleted_chunk_count: int,
        failure_code: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE index_generation
                SET deleted_chunk_count = ?, failure_code = ?
                WHERE generation_id = ? AND status = 'active'
                """,
                (deleted_chunk_count, failure_code, generation_id),
            )

    def active_index_generation(self) -> IndexGeneration | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM index_generation WHERE status = 'active'"
            ).fetchone()
        return self._index_generation_from_row(row) if row else None

    def get_index_generation(self, generation_id: str) -> IndexGeneration:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM index_generation WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown index generation: {generation_id}")
        return self._index_generation_from_row(row)

    def list_generation_chunk_ids(self, generation_id: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chunk_id FROM chunk_index_state
                WHERE generation_id = ? AND status = 'indexed'
                ORDER BY chunk_id
                """,
                (generation_id,),
            ).fetchall()
        return [row["chunk_id"] for row in rows]

    def mark_generation_chunks_deleted(self, generation_id: str) -> int:
        with self._connect() as connection:
            return connection.execute(
                """
                UPDATE chunk_index_state
                SET status = 'deleted', last_attempt_at = ?, failure_code = NULL
                WHERE generation_id = ? AND status = 'indexed'
                """,
                (_iso(datetime.now(UTC)), generation_id),
            ).rowcount

    def inspect_attraction(self, attraction_id: str) -> dict:
        with self._connect() as connection:
            attraction = connection.execute(
                "SELECT * FROM attraction WHERE attraction_id = ?",
                (attraction_id,),
            ).fetchone()
            versions = connection.execute(
                """
                SELECT version.*, source.url, source.title, source.source_type
                FROM document_version AS version
                JOIN source_document AS source ON source.source_id = version.source_id
                WHERE source.attraction_id = ?
                ORDER BY version.fetched_at DESC
                """,
                (attraction_id,),
            ).fetchall()
        if attraction is None:
            raise KeyError(f"Unknown attraction: {attraction_id}")
        return {
            "attraction": dict(attraction),
            "versions": [dict(row) for row in versions],
        }

    def find_attractions_in_text(self, text: str, *, limit: int = 2) -> list[Attraction]:
        """Resolve mentions from the governed attraction catalog, not a code registry."""
        normalized_text = text.casefold()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT attraction_id, name, aliases_json, city, country FROM attraction"
            ).fetchall()

        matches: list[tuple[int, int, Attraction]] = []
        removable_suffixes = ("博物院", "博物馆", "景区", "公园")
        for row in rows:
            aliases = [row["name"], *json.loads(row["aliases_json"] or "[]")]
            for suffix in removable_suffixes:
                if row["name"].endswith(suffix) and len(row["name"]) > len(suffix):
                    aliases.append(row["name"][: -len(suffix)])
            candidates = sorted({item for item in aliases if item}, key=len, reverse=True)
            found = [
                (normalized_text.find(alias.casefold()), len(alias))
                for alias in candidates
                if alias.casefold() in normalized_text
            ]
            if not found:
                continue
            position, matched_length = min(found, key=lambda item: (item[0], -item[1]))
            matches.append(
                (
                    position,
                    -matched_length,
                    Attraction(
                        attraction_id=row["attraction_id"],
                        name=row["name"],
                        aliases=json.loads(row["aliases_json"] or "[]"),
                        city=row["city"],
                        country=row["country"],
                    ),
                )
            )
        matches.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in matches[:limit]]

    @staticmethod
    def _version_from_row(row: sqlite3.Row) -> DocumentVersion:
        return DocumentVersion(
            version_id=row["version_id"],
            source_id=row["source_id"],
            content_hash=row["content_hash"],
            status=VersionStatus(row["status"]),
            fetched_at=_datetime(row["fetched_at"]),
            valid_from=_datetime(row["valid_from"]),
            valid_to=_datetime(row["valid_to"]),
            published_at=_datetime(row["published_at"]),
            supersedes_version_id=row["supersedes_version_id"],
            rejection_reason=row["rejection_reason"],
            hash_version=row["hash_version"], payload_hash=row["payload_hash"],
        )

    @staticmethod
    def _indexable_chunk_from_row(row: sqlite3.Row) -> IndexableChunk:
        return IndexableChunk(
            chunk_id=row["chunk_id"],
            document_version_id=row["document_version_id"],
            attraction_id=row["attraction_id"],
            fact_type=row["fact_type"],
            content=row["content"],
            locator=row["locator"],
            language=row["language"],
            content_hash=row["content_hash"],
            source_id=row["source_id"],
            source_url=row["source_url"],
            source_title=row["source_title"],
            source_type=row["source_type"],
            source_authority=row["source_authority"],
            valid_from=_datetime(row["valid_from"]),
            valid_to=_datetime(row["valid_to"]),
            published_at=_datetime(row["published_at"]),
            version_status=row["version_status"],
        )

    @staticmethod
    def _index_generation_from_row(row: sqlite3.Row) -> IndexGeneration:
        return IndexGeneration(
            generation_id=row["generation_id"],
            corpus_version=row["corpus_version"],
            embedding_model=row["embedding_model"],
            status=row["status"],
            started_at=_datetime(row["started_at"]),
            completed_at=_datetime(row["completed_at"]),
            indexed_chunk_count=row["indexed_chunk_count"],
            failed_chunk_count=row["failed_chunk_count"],
            deleted_chunk_count=row["deleted_chunk_count"],
            failure_code=row["failure_code"],
        )
