from pydantic import BaseModel, Field

from app.schemas.semantic_frame import AnswerModeDecision, SemanticFrame
from app.schemas.travel_task import TravelTask


class QueryUnderstandingResult(BaseModel):
    rewritten_query: str
    resolved_references: dict[str, str] = Field(default_factory=dict)
    missing_critical_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    travel_task: TravelTask
    semantic_frame: SemanticFrame | None = None
    confidence: float = 0.8
    key_concerns: list[str] = Field(default_factory=list)
