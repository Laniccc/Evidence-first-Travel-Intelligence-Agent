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
