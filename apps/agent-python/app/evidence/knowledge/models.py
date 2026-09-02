"""Contracts for a small, versioned attraction fact corpus."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator


class VersionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REJECTED = "rejected"


class FactType(StrEnum):
    OPENING_HOURS = "opening_hours"
    TICKET_PRICE = "ticket_price"
    RESERVATION = "reservation"
    TRANSPORT = "transport"
    ACCESSIBILITY = "accessibility"
    VISITOR_NOTICE = "visitor_notice"
    GENERAL_DESCRIPTION = "general_description"


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
    fact_type: FactType
    content: str = Field(min_length=1)
    locator: str | None = None
    language: str = "zh-CN"

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return " ".join(value.split())


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

    @property
    def content_hash(self) -> str:
        normalized = " ".join(self.content.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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


class SourceDocumentRecord(BaseModel):
    source_id: str
    attraction_id: str
    url: str
    title: str
    source_type: SourceType
    authority_score: float


SOURCE_AUTHORITY: dict[SourceType, float] = {
    SourceType.OFFICIAL: 1.0,
    SourceType.STRUCTURED: 0.85,
    SourceType.SEARCH: 0.55,
    SourceType.FORUM: 0.35,
    SourceType.MODEL_PRIOR: 0.1,
}
