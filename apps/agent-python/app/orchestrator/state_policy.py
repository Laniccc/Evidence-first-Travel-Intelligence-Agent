from pydantic import BaseModel

from app.orchestrator.actions import AgentActionType
from app.orchestrator.s5_information_domain_registry import placeholder_tool_names
from tools.ticketing.provider_config import TICKET_PROVIDER_TOOL_NAMES


class StateNodePolicy(BaseModel):
    state_name: str
    allowed_actions: list[AgentActionType]
    allowed_tools: list[str] = []
    allowed_subagents: list[str] = []
    max_steps: int = 3
    required_output_schema: str | None = None
    allow_final_answer: bool = False


QUERY_UNDERSTANDING_POLICY = StateNodePolicy(
    state_name="query_understanding",
    allowed_actions=[
        AgentActionType.UPDATE_STATE,
        AgentActionType.CALL_SUBAGENT,
        AgentActionType.ASK_CLARIFICATION,
        AgentActionType.FINISH_STATE,
        AgentActionType.FAIL_STATE,
    ],
    allowed_subagents=["place_entity_extractor", "semantic_frame_builder", "query_understanding"],
    max_steps=2,
    required_output_schema="QueryUnderstandingResult",
    allow_final_answer=False,
)

ANSWER_COMPOSITION_POLICY = StateNodePolicy(
    state_name="answer_composition",
    allowed_actions=[
        AgentActionType.UPDATE_STATE,
        AgentActionType.CALL_SUBAGENT,
        AgentActionType.FINISH_STATE,
        AgentActionType.FAIL_STATE,
    ],
    allowed_subagents=["composer_agent"],
    max_steps=2,
    required_output_schema="FinalAnswerDraft",
    allow_final_answer=True,
)

EVIDENCE_AGGREGATION_POLICY = StateNodePolicy(
    state_name="evidence_aggregation",
    allowed_actions=[
        AgentActionType.UPDATE_STATE,
        AgentActionType.CALL_SUBAGENT,
        AgentActionType.FINISH_STATE,
        AgentActionType.FAIL_STATE,
    ],
    allowed_subagents=[
        "evidence_curation_planner_agent",
        "claim_relevance_filter_agent",
        "evidence_conflict_analyzer_agent",
    ],
    max_steps=4,
    required_output_schema="EvidenceBrief",
    allow_final_answer=False,
)

EVIDENCE_PLANNING_TOOL_NAMES = [
    "official",
    "places",
    "weather",
    "reviews",
    "transit",
    "restaurant",
    "lodging",
    "search_mcp",
    "browser_mcp",
    "official_page_reader_mcp",
    "osm_mcp",
    "places_mcp",
    "geocode_mcp",
    "openmeteo_mcp",
    "weather_mcp",
    "climate_mcp",
    "wikipedia_mcp",
    "wikidata_mcp",
    "sqlite_mcp",
    "evidence_store_mcp",
    "baidu_place_search_mcp",
    "baidu_place_detail_mcp",
    "baidu_weather_mcp",
    "baidu_geocode_mcp",
    "baidu_reverse_geocode_mcp",
    "baidu_route_mcp",
    "baidu_route_matrix_mcp",
    "baidu_traffic_mcp",
    "baidu_ip_location_mcp",
    "seasonality",
    "knowledge_prior",
    "fallback",
    # legacy aliases accepted at policy guard via resolver
    "official_mcp",
] + sorted(placeholder_tool_names()) + sorted(TICKET_PROVIDER_TOOL_NAMES)

EVIDENCE_PLANNING_TOOL_NAMES = list(dict.fromkeys(EVIDENCE_PLANNING_TOOL_NAMES))

EVIDENCE_PLANNING_AND_TOOL_USE_POLICY = StateNodePolicy(
    state_name="evidence_planning_and_tool_use",
    allowed_actions=[
        AgentActionType.UPDATE_STATE,
        AgentActionType.CALL_TOOL,
        AgentActionType.CALL_SUBAGENT,
        AgentActionType.ASK_CLARIFICATION,
        AgentActionType.FINISH_STATE,
        AgentActionType.FAIL_STATE,
    ],
    allowed_tools=EVIDENCE_PLANNING_TOOL_NAMES,
    allowed_subagents=[
        "search_task_planner_agent",
        "keyword_search_agent",
    ],
    max_steps=18,
    required_output_schema="EvidencePlanningResult",
    allow_final_answer=False,
)
