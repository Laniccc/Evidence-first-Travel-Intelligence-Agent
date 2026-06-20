from pydantic import BaseModel, Field


class ToolTrace(BaseModel):
    tool_name: str
    input: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    status: str = "ok"
    error: str | None = None
