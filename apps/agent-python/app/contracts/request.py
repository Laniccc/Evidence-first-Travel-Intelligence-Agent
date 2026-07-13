"""Request contracts for the Agent HTTP API."""

from pydantic import BaseModel, Field


class AgentQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    session_id: str | None = None
    user_context: dict = Field(default_factory=dict)
    debug: bool = False


# Compatibility name used by the original Python Agent HTTP surface.
TravelQueryRequest = AgentQueryRequest
