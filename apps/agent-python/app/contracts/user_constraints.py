"""Shared internal user constraints carried into auditable retrieval artifacts."""

from pydantic import BaseModel, ConfigDict, Field


class UserConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    party: list[str] = Field(default_factory=list)
    pace: str | None = None
    budget: str | None = None
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
