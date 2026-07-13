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
