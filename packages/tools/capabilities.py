from enum import Enum

from pydantic import BaseModel, Field


class FreshnessLevel(str, Enum):
    LIVE = "live"
    DAILY = "daily"
    RECENT = "recent"
    STATIC = "static"
    UNKNOWN = "unknown"


class CostLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolCapability(BaseModel):
    tool_name: str
    capabilities: list[str] = Field(default_factory=list)
    supported_countries: list[str] = Field(default_factory=lambda: ["Japan", "China", "South Korea"])
    supported_cities: list[str] = Field(default_factory=list)
    freshness: FreshnessLevel = FreshnessLevel.RECENT
    confidence_by_capability: dict[str, float] = Field(default_factory=dict)
    cost_level: CostLevel = CostLevel.LOW
    latency_level: LatencyLevel = LatencyLevel.LOW
    requires_api_key: bool = False
    license_scope: str = "mock_mvp"
