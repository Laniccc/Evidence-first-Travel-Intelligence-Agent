from pydantic import BaseModel, Field

from app.schemas.semantic_frame import SemanticFrame
from app.schemas.travel_task import TravelTask


class QueryUnderstandingResult(BaseModel):
    rewritten_query: str
    semantic_frame: SemanticFrame | None = None
    travel_task: TravelTask
    resolved_references: dict[str, str] = Field(default_factory=dict)
    missing_critical_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    key_concerns: list[str] = Field(default_factory=list)
