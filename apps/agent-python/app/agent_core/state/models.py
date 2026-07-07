"""Agent Core state-space data models.

Structured record-oriented design for the Deep Research Agent:
Runs, Topics, Phases, Artifacts, Evidence, Quality Checks, Jobs,
Research Plans, Source Ratings, and Cross-Reference Results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


# ── helpers ──────────────────────────────────────────────────────────────────


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── RunState ──────────────────────────────────────────────────────────────────


class RunState(BaseModel):
    """Top-level run representing one user query."""

    run_id: str
    session_id: str | None = None
    raw_query: str
    status: Literal[
        "created",
        "running",
        "waiting",
        "blocked",
        "failed",
        "succeeded",
        "succeeded_limited",
        "blocked_need_evidence",
        "blocked_need_user",
        "failed_infrastructure",
    ] = "created"
    active_topic_ids: list[str] = Field(default_factory=list)
    current_phase: str | None = None
    final_artifact_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


# ── TopicState ────────────────────────────────────────────────────────────────


class TopicState(BaseModel):
    """One decomposed topic thread within a run."""

    topic_id: str
    run_id: str
    task_class: str
    user_question: str
    normalized_claim: str
    status: Literal[
        "not_started",
        "running",
        "blocked",
        "failed",
        "succeeded",
        "succeeded_limited",
        "blocked_need_evidence",
        "blocked_need_user",
    ] = "not_started"
    phase_order: list[str] = Field(default_factory=list)
    current_phase: str | None = None
    confidence: float | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


# ── PhaseState ────────────────────────────────────────────────────────────────


class PhaseState(BaseModel):
    """State of one phase within a run or topic thread."""

    phase_id: str
    run_id: str
    topic_id: str | None = None  # None => run-level phase
    phase_name: str
    status: str  # one of the lifecycle statuses
    attempt: int = 1
    input_artifact_refs: list[str] = Field(default_factory=list)
    output_artifact_refs: list[str] = Field(default_factory=list)
    quality_check_ref: str | None = None
    approved_artifact_id: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


# ── ArtifactRecord ────────────────────────────────────────────────────────────


class ArtifactRecord(BaseModel):
    """Versioned output of a phase."""

    artifact_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    artifact_type: str
    version: int = 1
    status: Literal[
        "draft", "pending_review", "approved", "rejected",
        "needs_revision", "superseded", "succeeded",
    ]
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    rejection_reasons: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: str = Field(default_factory=utc_now_iso)


# ── EvidenceRecord ────────────────────────────────────────────────────────────


class EvidenceRecord(BaseModel):
    """Raw evidence gathered during evidence_acquisition."""

    evidence_id: str
    run_id: str
    topic_id: str | None = None
    source_name: str
    source_url: str | None = None
    source_type: str
    source_tier: int = 3  # 1-5, 1=highest (new: source quality rating)
    fetched_at: str | None = None
    claims: list[dict[str, Any]] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    reliability: str = "unknown"
    usage_role: Literal[
        "unreviewed", "adopted", "rejected", "context", "contradiction",
    ] = "unreviewed"


# ── QualityCheckRecord ────────────────────────────────────────────────────────


class QualityCheckRecord(BaseModel):
    """Deterministic or LLM-assisted quality check on an artifact."""

    check_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    artifact_id: str
    status: Literal["pass", "needs_revision", "fail"]
    score: float
    blocking_issues: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


# ── JobRecord ─────────────────────────────────────────────────────────────────


class JobRecord(BaseModel):
    """External tool call or long-running action."""

    job_id: str
    run_id: str
    topic_id: str | None = None
    phase_name: str
    tool_name: str
    status: Literal[
        "queued", "running", "succeeded", "failed", "stale", "cancelled",
    ]
    input: dict[str, Any] = Field(default_factory=dict)
    output_ref: str | None = None
    error: str | None = None
    retry_count: int = 0
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


# ── Research Planning ─────────────────────────────────────────────────────────


class ResearchSubQuestion(BaseModel):
    """A single sub-question in a research plan."""

    question: str
    search_query: str
    search_sources: list[str] = Field(default_factory=list)  # academic, news, general, tech
    expected_claim_types: list[str] = Field(default_factory=list)


class ResearchPlanArtifact(BaseModel):
    """Output of the planning phase — decomposed research plan."""

    topic_title: str
    sub_questions: list[ResearchSubQuestion] = Field(default_factory=list)
    search_strategy: str = "balanced"  # broad, deep, balanced
    requires_clarification: bool = False
    clarification_question: str | None = None


# ── Source Rating ─────────────────────────────────────────────────────────────


class SourceRating(BaseModel):
    """Quality assessment of a single web source."""

    url: str
    domain: str
    tier: int  # 1-5, 1=highest
    tier_label: str = ""  # e.g. "权威来源", "高质量来源"
    confidence: float  # 0.0-1.0
    content_quality: str = "unknown"  # original, aggregated, low_effort, spam
    freshness_days: int | None = None
    relevance_score: float = 1.0


# ── Cross-Reference ───────────────────────────────────────────────────────────


class CrossReferenceResult(BaseModel):
    """Result of cross-referencing a factual claim against other sources."""

    claim: str
    source_refs: list[str] = Field(default_factory=list)
    corroborating_sources: int = 0
    conflicting_sources: int = 0
    status: Literal["verified", "unverified", "contested"] = "unverified"
    resolution_note: str | None = None


# ── Research Report ───────────────────────────────────────────────────────────


class ResearchReportArtifact(BaseModel):
    """Output of the synthesis phase — structured research report."""

    title: str
    summary: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    cross_references: list[CrossReferenceResult] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    overall_confidence: Literal["high", "medium", "low"] = "medium"
    word_count: int = 0


# ── Topic Draft (for knowledge_retrieval output) ──────────────────────────────


class TopicDraft(BaseModel):
    """A candidate topic before it is committed as a TopicState."""

    question: str
    normalized_query: str
    search_queries: list[str] = Field(default_factory=list)
    priority: str = "normal"


# ── Phase Tool Result ─────────────────────────────────────────────────────────


class AgentEvent(BaseModel):
    """An event emitted during phase execution (for debug/audit)."""

    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class PhaseToolResult(BaseModel):
    """Return value of every phase tool invocation."""

    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    quality_checks: list[QualityCheckRecord] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)


# ── Pipeline Gate ─────────────────────────────────────────────────────────────


class BlockedTool(BaseModel):
    """A tool that is currently blocked, with reason."""

    tool_name: str
    reason: str
    unblock_condition: str = ""


class ToolVisibility(BaseModel):
    """Describes which tools are visible to the root agent at a given moment."""

    phase_name: str
    topic_id: str | None = None
    allowed_phase_tools: list[str] = Field(default_factory=list)
    allowed_control_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[BlockedTool] = Field(default_factory=list)
    required_next_actions: list[str] = Field(default_factory=list)
    stop_reasons: list[str] = Field(default_factory=list)


# ── Projection (Read Model) ───────────────────────────────────────────────────


class TopicCard(BaseModel):
    """UI-visible summary of one topic thread."""

    topic_id: str
    task_class: str
    user_question: str
    status: str
    current_phase: str | None = None
    confidence: float | None = None


class PhaseCard(BaseModel):
    """UI-visible summary of one phase."""

    phase_id: str
    phase_name: str
    topic_id: str | None = None
    status: str
    attempt: int = 1
    approved_artifact_id: str | None = None
    error: str | None = None


class AdoptedFact(BaseModel):
    """A fact that was adopted into the final answer."""

    claim: str
    source_refs: list[str] = Field(default_factory=list)
    confidence: str = "medium"


class RejectedFact(BaseModel):
    """A fact that was rejected, with machine-readable reason."""

    claim: str
    reason: str
    source_refs: list[str] = Field(default_factory=list)


class EvidenceGap(BaseModel):
    """An identified gap in evidence coverage."""

    description: str
    priority: str = "medium"
    topic_id: str | None = None
    phase_name: str | None = None
    claim_type: str | None = None
    suggested_tools: list[str] = Field(default_factory=list)
    status: str = "open"


class RunProjection(BaseModel):
    """Read model for the supervisor, UI, debug report, and API response."""

    run_id: str
    status: str
    raw_query: str
    current_phase: str | None = None
    topic_cards: list[TopicCard] = Field(default_factory=list)
    phase_cards: list[PhaseCard] = Field(default_factory=list)
    adopted_facts: list[AdoptedFact] = Field(default_factory=list)
    rejected_facts: list[RejectedFact] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    visible_actions: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    final_answer: str | None = None
