"""Planning output describing required and optional research information."""

from pydantic import BaseModel, Field


class QueryPlan(BaseModel):
    required_info: list[str] = Field(default_factory=list)
    optional_info: list[str] = Field(default_factory=list)
    missing_but_acceptable: list[str] = Field(default_factory=list)
    must_ask_user: list[str] = Field(default_factory=list)
