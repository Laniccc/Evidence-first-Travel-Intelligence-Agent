from typing import Any

from pydantic import BaseModel, Field

from app.evidence.citation import CitationCheckResult
from app.context.conversation_context import ConversationContext, ConversationMemory
from app.planning.information_need_model import InformationNeed
from app.planning.query_plan import QueryPlan
from app.understanding.normalized_user_request import NormalizedUserRequest
from app.understanding.query_understanding_model import QueryUnderstandingResult
from app.understanding.travel_task import PlaceContext
from app.understanding.rewritten_query import RewrittenQueryResult
from app.observability.tool_trace import ToolTrace
from app.evidence.coverage_report import CoverageReport
from app.composition.response_contract import ResponseContract
from app.understanding.intent_profile import IntentProfile
from app.planning.s5_information_domain import S5DomainPlan
from app.planning.intent_strategy_registry import IntentStrategy
from app.understanding.semantic_frame_model import AnswerModeDecision, SemanticFrame
from app.evidence.evidence_brief_model import EvidenceBrief
from app.evidence.evidence_decision_report import EvidenceDecisionReport
from app.planning.evidence_gap_request import EvidenceGapLoopState, EvidenceGapRequest
from app.planning.user_need_residual import UserNeedResidual
from app.understanding.travel_task import TravelTask
from app.tools.tool_router import ToolExecutionPlan
from app.understanding.user_query import (
    BudgetLevel,
    IntentType,
    PaceType,
    PartyType,
    RegionGateResult,
    TransportPreference,
    UserContext,
    UserGoal,
)


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
    intent_profile: IntentProfile | None = None
    intent_strategy: IntentStrategy | None = None
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
    internal_debug_limitations: list[str] = Field(default_factory=list)
    user_visible_limitations: list[str] = Field(default_factory=list)
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
    comparison_mode: bool = False
    comparison_active_place: str | None = None
    comparison_peer_places: list[str] = Field(default_factory=list)
    agent_core_store: Any | None = Field(default=None, exclude=True)
