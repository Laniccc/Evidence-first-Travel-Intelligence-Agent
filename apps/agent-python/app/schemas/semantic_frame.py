from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.place_ambiguity import PlaceAmbiguityInfo


class QueryScope(str, Enum):
    PLACE = "place"
    CITY = "city"
    COUNTRY = "country"
    REGION = "region"
    ITINERARY = "itinerary"
    UNKNOWN = "unknown"


class TaskFamily(str, Enum):
    FACT_LOOKUP = "fact_lookup"
    SUITABILITY = "suitability"
    COMPARISON = "comparison"
    PLANNING = "planning"
    ADVISORY = "advisory"
    CROWD = "crowd"
    WEATHER = "weather"
    TRANSPORT = "transport"
    FOOD = "food"
    LODGING = "lodging"
    UNKNOWN = "unknown"


class DecisionType(str, Enum):
    BEST_TIME_TO_VISIT = "best_time_to_visit"
    WHETHER_TO_GO = "whether_to_go"
    HOW_TO_CHOOSE = "how_to_choose"
    RISK_CHECK = "risk_check"
    ROUTE_PLAN = "route_plan"
    NEARBY_SEARCH = "nearby_search"
    GENERAL_ADVICE = "general_advice"
    FACT_LOOKUP = "fact_lookup"
    UNKNOWN = "unknown"


class TimeScope(str, Enum):
    CURRENT = "current"
    SPECIFIC_DATE = "specific_date"
    MONTH = "month"
    SEASONAL = "seasonal"
    FLEXIBLE = "flexible"
    UNKNOWN = "unknown"


class SemanticEntities(BaseModel):
    country: str | None = None
    city: str | None = None
    places: list[str] = Field(default_factory=list)
    region: str | None = None


class SemanticFrame(BaseModel):
    raw_query: str
    normalized_request: str = ""
    query_scope: QueryScope = QueryScope.UNKNOWN
    task_family: TaskFamily = TaskFamily.UNKNOWN
    decision_type: DecisionType = DecisionType.UNKNOWN
    entities: SemanticEntities = Field(default_factory=SemanticEntities)
    time_scope: TimeScope = TimeScope.UNKNOWN
    user_constraints: list[str] = Field(default_factory=list)
    key_concerns: list[str] = Field(default_factory=list)
    information_needs: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    confidence: float = 0.7
    requires_live_data: bool = False
    requires_exact_fact: bool = False
    can_answer_with_model_prior: bool = False
    needs_clarification: bool = False
    place_ambiguity: PlaceAmbiguityInfo | None = None
    labeled_entities: list[dict] = Field(
        default_factory=list,
        description="S2 entities with labels — preserved for S3 gating",
    )


class AnswerMode(str, Enum):
    EVIDENCE_REQUIRED = "evidence_required"
    EVIDENCE_PREFERRED = "evidence_preferred"
    MODEL_PRIOR_ALLOWED = "model_prior_allowed"
    ESTIMATION_ALLOWED = "estimation_allowed"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"


class AnswerModeDecision(BaseModel):
    answer_mode: AnswerMode
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    allow_knowledge_prior: bool = False
    allow_partial_answer: bool = False
    limitations_to_add: list[str] = Field(default_factory=list)
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
