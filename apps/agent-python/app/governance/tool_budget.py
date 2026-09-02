"""Tool call budget for one Agent run."""

from pydantic import BaseModel, Field


class ToolBudget(BaseModel):
    max_calls: int = Field(default=30, ge=0)
    used_calls: int = Field(default=0, ge=0)

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.used_calls)

    def can_call(self, amount: int = 1) -> bool:
        return amount >= 0 and self.used_calls + amount <= self.max_calls

    def consume(self, amount: int = 1) -> "ToolBudget":
        if not self.can_call(amount):
            raise ValueError("Tool budget exceeded")
        return self.model_copy(update={"used_calls": self.used_calls + amount})


class RunBudget(BaseModel):
    """Small deterministic budget used by the state runtime."""

    max_steps: int = Field(default=24, ge=1)
    max_tool_calls: int = Field(default=1, ge=0)
    used_steps: int = Field(default=0, ge=0)
    used_tool_calls: int = Field(default=0, ge=0)

    def consume_step(self) -> "RunBudget":
        if self.used_steps >= self.max_steps:
            raise ValueError("State step budget exceeded")
        return self.model_copy(update={"used_steps": self.used_steps + 1})

    def consume_tool_call(self) -> "RunBudget":
        if self.used_tool_calls >= self.max_tool_calls:
            raise ValueError("Tool call budget exceeded")
        return self.model_copy(update={"used_tool_calls": self.used_tool_calls + 1})
