"""Generic API response models."""

from pydantic import BaseModel, Field


class TraceStep(BaseModel):
    step: str
    status: str = "completed"
    detail: str | None = None


class GenericResponse(BaseModel):
    """Generic API response wrapper."""
    answer: str = ""
    status: str = "ok"
    confidence: float = 0.0
    limitations: list[str] = Field(default_factory=list)
    tool_traces: list[dict] = Field(default_factory=list)
    session_id: str | None = None
    query_id: str | None = None

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault("mode", "json")
        return super().model_dump(*args, **kwargs)
