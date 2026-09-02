"""Audit-complete retrieval report contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.fusion import FusionCandidate


class RetrievalAttempt(BaseModel):
    channel: Literal["lexical", "dense"]
    status: Literal["success", "empty", "failed"]
    result_count: int = 0
    latency_ms: float = Field(ge=0)
    failure_code: str | None = None


class PostFilterRejection(BaseModel):
    chunk_id: str
    reason: Literal[
        "pending_version",
        "superseded_version",
        "expired_version",
        "hash_mismatch",
        "missing_chunk",
    ]
    channel: str | None = None


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_version_id: str
    attraction_id: str
    fact_type: str
    content: str
    source_id: str
    source_url: str
    source_title: str
    source_authority: float
    content_hash: str
    locator: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    retrieval_channels: list[Literal["lexical", "dense"]]
    rrf_score: float
    final_score: float
    corpus_version: str


class LatencyBreakdown(BaseModel):
    lexical_ms: float = Field(ge=0)
    dense_ms: float = Field(ge=0)
    fusion_ms: float = Field(ge=0)
    post_filter_rerank_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class RetrievalReport(BaseModel):
    subtask_id: str
    retrieval_plan: RetrievalPlan
    corpus_version: str
    index_generation: str | None = None
    embedding_model: str | None = None
    lexical_attempt: RetrievalAttempt
    dense_attempt: RetrievalAttempt
    fusion_candidates: list[FusionCandidate] = Field(default_factory=list)
    post_filter_rejections: list[PostFilterRejection] = Field(default_factory=list)
    final_hits: list[RetrievedChunk] = Field(default_factory=list)
    coverage_hints: list[str] = Field(default_factory=list)
    degradation: Literal[
        "none", "lexical_only", "dense_only", "all_failed", "no_results"
    ]
    latency_breakdown: LatencyBreakdown
