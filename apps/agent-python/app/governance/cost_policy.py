"""Cost controls for one Agent run."""

from pydantic import BaseModel, Field


class CostMetric(BaseModel):
    llm_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    estimated_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)


class CostPolicy(BaseModel):
    max_llm_calls: int = Field(default=8, ge=0)
    max_tool_calls: int = Field(default=30, ge=0)
    max_estimated_cost_usd: float = Field(default=1.0, ge=0.0)

    def allows(self, metric: CostMetric) -> bool:
        return (
            metric.llm_calls <= self.max_llm_calls
            and metric.tool_calls <= self.max_tool_calls
            and metric.estimated_cost_usd <= self.max_estimated_cost_usd
        )
