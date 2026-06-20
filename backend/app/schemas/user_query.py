from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.citation import CitationCheckResult
from app.schemas.conversation_context import ConversationContext
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.information_need import InformationNeed
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.place_context import PlaceContext
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.tool_trace import ToolTrace
from app.schemas.semantic_frame import AnswerModeDecision, SemanticFrame
from app.schemas.travel_task import TravelTask
from app.tools.tool_router import ToolExecutionPlan


class IntentType(str, Enum):
    SINGLE_PLACE = "single_place"
    COMPARE_PLACES = "compare_places"
    ITINERARY = "itinerary"
    TRANSPORT = "transport"
    FOOD_LODGING = "food_lodging"
    WEATHER_RISK = "weather_risk"
    GENERAL = "general"


class PartyType(str, Enum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    ELDERLY = "elderly"
    CHILDREN = "children"
    FRIENDS = "friends"


class BudgetLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class PaceType(str, Enum):
    RELAXED = "relaxed"
    NORMAL = "normal"
    INTENSE = "intense"
    UNKNOWN = "unknown"


class TransportPreference(str, Enum):
    PUBLIC_TRANSPORT = "public_transport"
    TAXI = "taxi"
    WALKING = "walking"
    DRIVING = "driving"
    UNKNOWN = "unknown"


class UserContext(BaseModel):
    travel_date: str | None = None
    party: list[PartyType] = Field(default_factory=list)
    pace: PaceType = PaceType.UNKNOWN
    transport_preference: TransportPreference = TransportPreference.UNKNOWN
    budget_level: BudgetLevel = BudgetLevel.UNKNOWN
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    start_location: str | None = None


class UserGoal(BaseModel):
    intent_type: IntentType = IntentType.GENERAL
    destination_country: str | None = None
    destination_city: str | None = None
    place_candidates: list[str] = Field(default_factory=list)
    travel_date: str | None = None
    start_location: str | None = None
    party: list[PartyType] = Field(default_factory=list)
    budget_level: BudgetLevel = BudgetLevel.UNKNOWN
    pace: PaceType = PaceType.UNKNOWN
    transport_preference: TransportPreference = TransportPreference.UNKNOWN
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class RegionGateResult(BaseModel):
    supported: bool
    country: str | None = None
    city: str | None = None
    reason: str = ""


class QueryPlan(BaseModel):
    required_info: list[str] = Field(default_factory=list)
    optional_info: list[str] = Field(default_factory=list)
    missing_but_acceptable: list[str] = Field(default_factory=list)
    must_ask_user: list[str] = Field(default_factory=list)


class SuitabilityScores(BaseModel):
    overall_suitability: float | None = None
    confidence: float | None = None
    crowd_risk: float | None = None
    weather_risk: float | None = None
    walking_intensity: float | None = None
    elderly_friendliness: float | None = None
    family_friendliness: float | None = None
    transport_convenience: float | None = None
    value_for_money: float | None = None


class ConflictRecord(BaseModel):
    field: str
    description: str
    sources: list[str] = Field(default_factory=list)
    resolution: str = ""


class TravelAgentState(BaseModel):
    session_id: str
    query_id: str
    raw_user_query: str
    next_state: str | None = None
    region_gate: RegionGateResult | None = None
    conversation_memory: ConversationMemory | None = None
    conversation_context: ConversationContext | None = None
    query_understanding: QueryUnderstandingResult | None = None
    rewritten_query_result: RewrittenQueryResult | None = None
    travel_task: TravelTask | None = None
    semantic_frame: SemanticFrame | None = None
    answer_mode_decision: AnswerModeDecision | None = None
    information_needs: list[InformationNeed] = Field(default_factory=list)
    tool_execution_plan: ToolExecutionPlan | None = None
    user_goal: UserGoal | None = None
    query_plan: QueryPlan | None = None
    place_contexts: list[PlaceContext] = Field(default_factory=list)
    evidence: list = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    review_aspects: list = Field(default_factory=list)
    scores: SuitabilityScores = Field(default_factory=SuitabilityScores)
    visible_trace: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    field_evidence_summary: list[dict] = Field(default_factory=list)
    citation_check_result: CitationCheckResult | None = None
    tool_traces: list[ToolTrace] = Field(default_factory=list)
    final_response: str | None = None
    structured_result: dict | None = None
    recommendations: list[dict] = Field(default_factory=list)
