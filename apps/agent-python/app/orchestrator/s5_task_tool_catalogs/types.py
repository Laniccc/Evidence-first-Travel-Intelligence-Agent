"""Tool card schema for S5 LLM tool selection."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentToolDefinition(BaseModel):
    """Rich tool card exposed to LLM controllers (when_to_use, params, prerequisites)."""

    name: str
    summary: str
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    parameters: dict[str, str] = Field(default_factory=dict)
    prerequisites: list[str] = Field(default_factory=list)
    satisfies_needs: list[str] = Field(default_factory=list)
    call_order_hint: str = ""

    def to_prompt_dict(self) -> dict:
        return {
            "name": self.name,
            "summary": self.summary,
            "when_to_use": self.when_to_use,
            "when_not_to_use": self.when_not_to_use,
            "parameters": self.parameters,
            "prerequisites": self.prerequisites,
            "satisfies_needs": self.satisfies_needs,
            "call_order_hint": self.call_order_hint or None,
        }
