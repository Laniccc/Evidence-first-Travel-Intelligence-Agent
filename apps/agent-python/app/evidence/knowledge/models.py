"""Contracts for a small, versioned attraction fact corpus."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator
from app.contracts.fact_type import FactType


class VersionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"


class IndexGenerationStatus(StrEnum):
    PENDING = "pending"
    BUILDING = "building"
    ACTIVE = "active"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class ChunkIndexStatus(StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class SourceType(StrEnum):
    OFFICIAL = "official"
    STRUCTURED = "structured"
    SEARCH = "search"
    FORUM = "forum"
    MODEL_PRIOR = "model_prior"


class Attraction(BaseModel):
    attraction_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    city: str | None = None
    country: str | None = None


class FactChunkDraft(BaseModel):
    chunk_id: str | None = None
    fact_type: FactType
    content: str = Field(min_length=1)
    locator: str | None = None
    language: str = "zh-CN"

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("chunk_id")
    @classmethod
    def reject_blank_chunk_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("chunk_id must not be blank")
        return value


class KnowledgeDocument(BaseModel):
    source_id: str = Field(min_length=1)
    attraction: Attraction
    url: str
    title: str = Field(min_length=1)
    source_type: SourceType
    content: str = Field(min_length=1)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    chunks: list[FactChunkDraft] = Field(min_length=1)
    payload_hash: str | None = None

    @property
    def content_hash(self) -> str:
        def utc(value):
            return value.replace(tzinfo=UTC).isoformat() if value and value.tzinfo is None else value.astimezone(UTC).isoformat() if value else None
        canonical = {"schema_version": 2, "source_id": self.source_id,
            "attraction_id": self.attraction.attraction_id, "url": self.url,
            "title": self.title, "source_type": self.source_type.value,
            "content": " ".join(self.content.split()),
            "facts": [c.model_dump(mode="json", exclude={"chunk_id"}) for c in self.chunks],
            "valid_from": utc(self.valid_from), "valid_to": utc(self.valid_to)}
        return hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()


class IngestResult(BaseModel):
    source_id: str
    version_id: str
    content_hash: str
    status: VersionStatus
    created: bool


class DocumentVersion(BaseModel):
    version_id: str
    source_id: str
    content_hash: str
    status: VersionStatus
    fetched_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    published_at: datetime | None = None
    supersedes_version_id: str | None = None
    rejection_reason: str | None = None
    hash_version: int = 1
    payload_hash: str | None = None


class SourceDocumentRecord(BaseModel):
    source_id: str
    attraction_id: str
    url: str
    title: str
    source_type: SourceType
    authority_score: float


class IndexableChunk(BaseModel):
    chunk_id: str
    document_version_id: str
    attraction_id: str
    fact_type: FactType
    content: str
    locator: str | None = None
    language: str
    content_hash: str
    source_id: str
    source_url: str
    source_title: str
    source_type: SourceType
    source_authority: float
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    published_at: datetime | None = None
    version_status: VersionStatus


class IndexGeneration(BaseModel):
    generation_id: str
    corpus_version: str
    embedding_model: str
    status: IndexGenerationStatus
    started_at: datetime
    completed_at: datetime | None = None
    indexed_chunk_count: int = 0
    failed_chunk_count: int = 0
    deleted_chunk_count: int = 0
    failure_code: str | None = None


class IndexSyncResult(BaseModel):
    generation_id: str
    corpus_version: str
    embedding_model: str
    status: IndexGenerationStatus
    indexed_chunk_count: int = 0
    failed_chunk_count: int = 0
    deleted_chunk_count: int = 0
    reused: bool = False
    cleanup_failure_code: str | None = None


SOURCE_AUTHORITY: dict[SourceType, float] = {
    SourceType.OFFICIAL: 1.0,
    SourceType.STRUCTURED: 0.85,
    SourceType.SEARCH: 0.55,
    SourceType.FORUM: 0.35,
    SourceType.MODEL_PRIOR: 0.1,
}
