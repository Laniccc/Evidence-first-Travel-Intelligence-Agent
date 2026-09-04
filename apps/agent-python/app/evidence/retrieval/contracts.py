"""Typed contracts at the vector retrieval boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.contracts.vector_index import VectorFilters, VectorHit, VectorPoint
from app.contracts.user_constraints import UserConstraints
from app.evidence.knowledge.models import FactType

__all__ = ["RetrievalPlan", "VectorFilters", "VectorHit", "VectorPoint"]


class RetrievalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_type: Literal["fact_query", "suitability", "comparison"]
    query_text: str = Field(min_length=1)
    attraction_ids: list[str] = Field(min_length=1, max_length=2)
    fact_types: list[FactType] = Field(default_factory=list)
    as_of: AwareDatetime
    top_k: int = Field(default=3, ge=1, le=5)
    subtask_id: str = Field(min_length=1)
    raw_query: str | None = None
    lexical_query: str | None = Field(default=None, min_length=1, max_length=2000)
    user_constraints: UserConstraints = Field(default_factory=UserConstraints)
    require_explicit_temporal_coverage: bool = False
