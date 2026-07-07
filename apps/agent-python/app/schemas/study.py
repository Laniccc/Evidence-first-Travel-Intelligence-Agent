"""Research Agent query/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StudyQueryRequest(BaseModel):
    """Incoming research query from user."""
    query: str = Field(..., min_length=10, max_length=2000, description="Research topic or question")
    session_id: str | None = Field(None, description="Session for conversation continuity")
    user_context: dict[str, Any] = Field(default_factory=dict, description="Optional user preferences")
    debug: bool = Field(False, description="Enable debug mode (returns phase traces)")


class SourceInfo(BaseModel):
    """A cited source in the research report."""
    id: int
    title: str
    url: str
    tier: int = 3
    tier_label: str = ""


class StudyReport(BaseModel):
    """Structured research report."""
    title: str
    summary: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[SourceInfo] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    overall_confidence: str = "medium"
    word_count: int = 0


class StudyQueryResponse(BaseModel):
    """Response returned to the user."""
    status: str  # "completed", "partial", "clarification_needed", "error"
    run_id: str | None = None
    report: StudyReport | None = None
    message: str | None = None
    evidence_count: int = 0
    phases_completed: list[str] = Field(default_factory=list)
    tool_traces: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None
