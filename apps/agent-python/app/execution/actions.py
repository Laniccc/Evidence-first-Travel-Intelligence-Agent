from enum import Enum

from pydantic import BaseModel, Field


class AgentActionType(str, Enum):
    UPDATE_STATE = "update_state"
    CALL_SUBAGENT = "call_subagent"
    CALL_TOOL = "call_tool"
    ASK_CLARIFICATION = "ask_clarification"
    FINISH_STATE = "finish_state"
    FAIL_STATE = "fail_state"


class AgentAction(BaseModel):
    action_type: AgentActionType
    target: str | None = None
    arguments: dict = Field(default_factory=dict)
    expected_output_schema: str | None = None
    confidence: float = 0.0
    reason_summary: str = ""


class ActionResult(BaseModel):
    ok: bool = True
    output: dict = Field(default_factory=dict)
    error: str | None = None
