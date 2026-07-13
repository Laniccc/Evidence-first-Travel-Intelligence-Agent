"""Runtime timeout policy for tool execution."""

from pydantic import BaseModel, Field


class TimeoutPolicy(BaseModel):
    default_seconds: float = Field(default=15.0, gt=0)
    by_tool: dict[str, float] = Field(default_factory=dict)

    def seconds_for(self, tool_name: str | None) -> float:
        if tool_name and tool_name in self.by_tool:
            return self.by_tool[tool_name]
        return self.default_seconds
