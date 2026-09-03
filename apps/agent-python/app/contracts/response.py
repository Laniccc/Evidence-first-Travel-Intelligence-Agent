"""Response contracts for the Agent HTTP API."""

from typing import Any

from pydantic import BaseModel, Field


class AgentHealthResponse(BaseModel):
    status: str
    service: str
    version: str
    llm_mode: str = "not_required"
    llm_configured: bool = False
    ready: bool | None = None
    checks: dict[str, str] = Field(default_factory=dict)


class AgentQueryResponse(BaseModel):
    answer: str
    session_id: str | None = None
    query_id: str | None = None
    visible_trace: list[str] = Field(default_factory=list)
    evidence_summary: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    tool_traces: list[dict] = Field(default_factory=list)
    structured_result: Any | None = None
    field_evidence_summary: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    citation_check_result: dict | None = None
    semantic_frame_summary: dict | None = None
    answer_mode: str | None = None
    orchestration_summary: dict | None = None
    answer_claims: list[dict] = Field(default_factory=list)
    citation_report: dict | None = None
    retrieval_reports: list[dict] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)

    @classmethod
    def from_legacy(cls, result, session_id: str | None = None) -> "AgentQueryResponse":
        structured = result.structured_result
        return cls(
            answer=result.answer,
            session_id=result.session_id or session_id,
            query_id=result.query_id,
            visible_trace=list(result.visible_trace or []),
            evidence_summary=list(result.evidence_summary or []),
            limitations=list(result.limitations or []),
            confidence=float(result.confidence or 0.0),
            tool_traces=list(result.tool_traces or []),
            structured_result=structured.model_dump() if hasattr(structured, "model_dump") else structured,
            field_evidence_summary=list(result.field_evidence_summary or []),
            conflicts=list(result.conflicts or []),
            citation_check_result=result.citation_check_result,
            semantic_frame_summary=result.semantic_frame_summary,
            answer_mode=result.answer_mode,
            orchestration_summary=getattr(result, "orchestration_summary", None),
        )


# Compatibility name used by the original Python Agent HTTP surface.
TravelQueryResponse = AgentQueryResponse
