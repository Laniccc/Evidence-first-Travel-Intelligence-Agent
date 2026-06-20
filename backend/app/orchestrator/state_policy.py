from pydantic import BaseModel

from app.orchestrator.actions import AgentActionType


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
