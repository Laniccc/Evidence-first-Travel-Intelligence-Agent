"""Experimental Agent Core records for phase-based pipeline projection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PhaseStateRecord(BaseModel):
    run_id: str
    phase: str
    status: str = "not_started"
    attempt: int = 1
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    error: str | None = None
    updated_at: str = Field(default_factory=utc_now_iso)


class PhaseOutputRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    phase: str
    kind: str
    status: str = "draft"
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: str = Field(default_factory=utc_now_iso)


class EvidenceRecord(BaseModel):
    id: str
    run_id: str
    claim_id: str | None = None
    source_type: str
    source_name: str
    source_url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    strength: str = "unknown"
    usage_role: str = "context"
    created_at: str = Field(default_factory=utc_now_iso)


class ArtifactRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    artifact_type: str
    status: str = "draft"
    payload: dict[str, Any] = Field(default_factory=dict)
    cited_evidence_refs: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class ResearchPlanClaim(BaseModel):
    claim_type: str
    claim_family: str | None = None
    claim_description: str | None = None
    priority: str = "important"
    requires_exact_fact: bool = False
    requires_live_data: bool = False
    freshness: str | None = None
    allowed_source_types: list[str] = Field(default_factory=list)
    source_families: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    sequence_key: str | None = None
    tool_sequence: list[str] = Field(default_factory=list)
    must_attempt: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    max_attempts: int | None = None
    model_prior_allowed: bool = False
    estimation_allowed: bool = False
    missing_behavior: str | None = None
    notes: list[str] = Field(default_factory=list)


class ResearchPlanRecord(BaseModel):
    run_id: str
    task_class: str
    intent_family: str | None = None
    user_goal_summary: str = ""
    anchor_keywords: list[str] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    claim_plans: list[ResearchPlanClaim] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    blocked_tools: list[dict[str, str]] = Field(default_factory=list)
    source_family_plan: list[str] = Field(default_factory=list)
    budgets: dict[str, Any] = Field(default_factory=dict)
    phase_order: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    tool_name: str
    status: str = "queued"
    input: dict[str, Any] = Field(default_factory=dict)
    output_ref: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ControlToolResult(BaseModel):
    tool_name: str
    status: str
    message: str = ""
    phase: str | None = None
    job_id: str | None = None
    projection: dict[str, Any] | None = None


class PipelineStateProjection(BaseModel):
    run_id: str
    current_phase: str | None = None
    phase_status: dict[str, str] = Field(default_factory=dict)
    latest_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    claim_decisions: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    latest_artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    job_status: dict[str, int] = Field(default_factory=dict)
