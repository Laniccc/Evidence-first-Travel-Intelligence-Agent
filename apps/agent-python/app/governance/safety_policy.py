"""Safety and policy guard facade."""

from pydantic import BaseModel, Field

from app.governance.policy_guard import PolicyGuard


class SafetyPolicy(BaseModel):
    allow_external_tools: bool = True
    require_evidence_for_facts: bool = True
    blocked_tool_names: set[str] = Field(default_factory=set)

    def allows_tool(self, tool_name: str) -> bool:
        return self.allow_external_tools and tool_name not in self.blocked_tool_names


__all__ = ["PolicyGuard", "SafetyPolicy"]
