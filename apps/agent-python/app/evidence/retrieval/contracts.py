"""Typed contracts at the vector retrieval boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.evidence.knowledge.models import FactType


class VectorPoint(BaseModel):
    chunk_id: str = Field(min_length=1)
    vector: list[float] = Field(min_length=1)
    attraction_id: str = Field(min_length=1)
    fact_type: str = Field(min_length=1)
    document_version_id: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)


class VectorFilters(BaseModel):
    attraction_ids: list[str] = Field(min_length=1)
    fact_types: list[str] = Field(default_factory=list)
    corpus_version: str | None = None

    @field_validator("attraction_ids", "fact_types")
    @classmethod
    def unique_values(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class VectorHit(BaseModel):
    chunk_id: str
    score: float
    payload: dict


class RetrievalPlan(BaseModel):
    task_type: Literal["fact_query", "suitability", "comparison"]
    query_text: str = Field(min_length=1)
    attraction_ids: list[str] = Field(min_length=1, max_length=2)
    fact_types: list[FactType] = Field(default_factory=list)
    as_of: datetime
    top_k: int = Field(default=3, ge=1, le=5)
    subtask_id: str = Field(min_length=1)
