from pydantic import BaseModel, Field


class TraceStep(BaseModel):
    step: str
    status: str = "completed"
    detail: str | None = None


class ComparisonRow(BaseModel):
    place_name: str
    suitability: str
    transport: str
    walking_intensity: str
    crowd_risk: str
    highlights: str
    risks: str
    recommended_for: str


class RecommendationResult(BaseModel):
    overall_recommendation: str
    overall_score: float = 0.0
    confidence: float = 0.0
    best_for: list[str] = Field(default_factory=list)
    not_ideal_for: list[str] = Field(default_factory=list)
    recommended_time: str | None = None
    main_reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class StructuredResult(BaseModel):
    status: str | None = None
    recommendation: RecommendationResult | None = None
    places: list[dict] = Field(default_factory=list)
    comparison: list[ComparisonRow] | None = None
    itinerary: dict | None = None


class TravelQueryRequest(BaseModel):
    query: str
    user_context: dict = Field(default_factory=dict)
    debug: bool = False


class TravelQueryResponse(BaseModel):
    answer: str
    structured_result: StructuredResult
    visible_trace: list[str] = Field(default_factory=list)
    evidence_summary: list[dict] = Field(default_factory=list)
    field_evidence_summary: list[dict] = Field(default_factory=list)
    conflicts: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    citation_check_result: dict | None = None
    tool_traces: list[dict] = Field(default_factory=list)
    session_id: str | None = None
    query_id: str | None = None
    semantic_frame_summary: dict | None = None
    answer_mode: str | None = None
    orchestration_summary: dict | None = None
