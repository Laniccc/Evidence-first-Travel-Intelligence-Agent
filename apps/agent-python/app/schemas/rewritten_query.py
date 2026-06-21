from pydantic import BaseModel, Field


class RewrittenQueryResult(BaseModel):
    rewritten_query: str
    resolved_references: dict[str, str] = Field(default_factory=dict)
    missing_critical_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_prompt: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    key_concerns: list[str] = Field(default_factory=list)
