"""Typed contracts at the vector retrieval boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.contracts.vector_index import VectorFilters, VectorHit, VectorPoint
from app.evidence.knowledge.models import FactType

__all__ = ["RetrievalPlan", "VectorFilters", "VectorHit", "VectorPoint"]


class RetrievalPlan(BaseModel):
    task_type: Literal["fact_query", "suitability", "comparison"]
    query_text: str = Field(min_length=1)
    attraction_ids: list[str] = Field(min_length=1, max_length=2)
    fact_types: list[FactType] = Field(default_factory=list)
    as_of: datetime
    top_k: int = Field(default=3, ge=1, le=5)
    subtask_id: str = Field(min_length=1)
