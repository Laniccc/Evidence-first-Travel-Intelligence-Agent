"""Technology-neutral contracts for a rebuildable vector index."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class VectorPoint(BaseModel):
    chunk_id: str = Field(min_length=1)
    vector: list[float] = Field(min_length=1)
    attraction_id: str = Field(min_length=1)
    fact_type: str = Field(min_length=1)
    document_version_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_authority: float = Field(ge=0, le=1)
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class VectorFilters(BaseModel):
    attraction_ids: list[str] = Field(min_length=1)
    fact_types: list[str] = Field(default_factory=list)
    corpus_version: str | None = None
    embedding_model: str | None = None

    @field_validator("attraction_ids", "fact_types")
    @classmethod
    def unique_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class VectorHit(BaseModel):
    chunk_id: str
    score: float
    payload: dict
