"""Contract-aligned API models (see contracts/schemas/)."""

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: str | None = None
    user_context: dict = Field(default_factory=dict)
    debug: bool = False


class AgentQueryResponse(BaseModel):
    answer: str
    session_id: str | None = None
    query_id: str | None = None
    visible_trace: list[str] = Field(default_factory=list)
    evidence_summary: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    tool_traces: list[dict] = Field(default_factory=list)
    structured_result: dict | None = None
    field_evidence_summary: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    citation_check_result: dict | None = None
    semantic_frame_summary: dict | None = None
    answer_mode: str | None = None

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
            structured_result=structured.model_dump() if structured is not None else None,
            field_evidence_summary=list(result.field_evidence_summary or []),
            conflicts=list(result.conflicts or []),
            citation_check_result=result.citation_check_result,
            semantic_frame_summary=result.semantic_frame_summary,
            answer_mode=result.answer_mode,
        )
