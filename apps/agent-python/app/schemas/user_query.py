from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.citation import CitationCheckResult
from app.schemas.conversation_context import ConversationContext
from app.schemas.conversation_memory import ConversationMemory
from app.schemas.information_need import InformationNeed
from app.schemas.normalized_user_request import NormalizedUserRequest
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.place_context import PlaceContext
from app.schemas.rewritten_query import RewrittenQueryResult
from app.schemas.tool_trace import ToolTrace
from app.schemas.coverage_report import CoverageReport
from app.schemas.response_contract import ResponseContract
from app.schemas.s5_information_domain import S5DomainPlan
from app.schemas.semantic_frame import AnswerModeDecision, SemanticFrame
from app.schemas.evidence_brief import EvidenceBrief
from app.schemas.evidence_decision_report import EvidenceDecisionReport
from app.schemas.evidence_gap_request import EvidenceGapLoopState, EvidenceGapRequest
from app.schemas.user_need_residual import UserNeedResidual
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
    location_usage_allowed: bool = False


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
    normalized_request: NormalizedUserRequest | None = None
    query_understanding: QueryUnderstandingResult | None = None
    rewritten_query_result: RewrittenQueryResult | None = None
    travel_task: TravelTask | None = None
    semantic_frame: SemanticFrame | None = None
    answer_mode_decision: AnswerModeDecision | None = None
    response_contract: ResponseContract | None = None
    s5_domain_plan: S5DomainPlan | None = None
    coverage_report: CoverageReport | None = None
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
    evidence_planning_completed: bool = False
    evidence_accumulated: bool = False
    user_need_residual: UserNeedResidual | None = None
    evidence_brief: EvidenceBrief | None = None
    evidence_decision_report: EvidenceDecisionReport | None = None
    gap_loop_state: EvidenceGapLoopState | None = None
    current_evidence_gap_request: EvidenceGapRequest | None = None
    pending_evidence_gap_requests: list[EvidenceGapRequest] = Field(default_factory=list)
    planning_notes: list[str] = Field(default_factory=list)
    final_response: str | None = None
    structured_result: dict | None = None
    recommendations: list[dict] = Field(default_factory=list)
