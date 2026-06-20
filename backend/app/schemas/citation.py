from pydantic import BaseModel, Field


class CitationCheckResult(BaseModel):
    confidence: float
    limitations: list[str] = Field(default_factory=list)
    unsupported_or_mismatched_claims: list[dict] = Field(default_factory=list)
