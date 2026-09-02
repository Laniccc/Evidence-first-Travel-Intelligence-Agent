"""SQLite repository for attraction knowledge lifecycle state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from app.evidence.knowledge.models import (
    DocumentVersion,
    IngestResult,
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
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path = Path(__file__).with_name("schema.sql")
        with self._connect() as connection:
            connection.executescript(schema_path.read_text(encoding="utf-8"))

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
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
        now = _iso(datetime.now(UTC))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO attraction(
                    attraction_id, name, aliases_json, city, country, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(attraction_id) DO UPDATE SET
                    name = excluded.name,
                    aliases_json = excluded.aliases_json,
                    city = excluded.city,
                    country = excluded.country,
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
                    valid_from, valid_to, supersedes_version_id
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
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
                ),
            )
            for chunk in document.chunks:
                connection.execute(
                    """
                    INSERT INTO fact_chunk(
                        chunk_id, version_id, attraction_id, fact_type, content, locator, language
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"chunk-{uuid4()}",
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
            row = connection.execute(
                "SELECT source_id, status FROM document_version WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown document version: {version_id}")
            if row["status"] == VersionStatus.REJECTED.value:
                raise ValueError("A rejected version cannot be published")
            if row["status"] == VersionStatus.EXPIRED.value:
                raise ValueError("An expired version cannot be published")
            if row["status"] != VersionStatus.ACTIVE.value:
                connection.execute(
                    """
                    UPDATE document_version
                    SET status = 'superseded'
                    WHERE source_id = ? AND status = 'active' AND version_id <> ?
                    """,
                    (row["source_id"], version_id),
                )
                connection.execute(
                    """
                    UPDATE document_version
                    SET status = 'active', published_at = ?, rejection_reason = NULL
                    WHERE version_id = ?
                    """,
                    (_iso(datetime.now(UTC)), version_id),
                )
        return self.get_version(version_id)

    def reject(self, version_id: str, *, reason: str) -> DocumentVersion:
        with self._connect() as connection:
            changed = connection.execute(
                """
                UPDATE document_version
                SET status = 'rejected', rejection_reason = ?
                WHERE version_id = ? AND status <> 'active'
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
        )
