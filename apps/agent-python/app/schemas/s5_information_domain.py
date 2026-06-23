"""S5 information acquisition framework: Domain → Provider Group → MCP Tool."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class InformationDomain(str, Enum):
    GEO_RESOLUTION = "geo_resolution"
    TICKET_BOOKING = "ticket_booking"
    OPERATION_STATUS = "operation_status"
    SEASONALITY = "seasonality"
    ROUTE_PLANNING = "route_planning"
    REVIEW_SIGNAL = "review_signal"
    NEARBY_RECOMMENDATION = "nearby_recommendation"
    REALTIME_STATUS = "realtime_status"


class ProviderGroup(str, Enum):
    BAIDU_LBS_PROVIDER = "baidu_lbs_provider"
    OFFICIAL_WEB_PROVIDER = "official_web_provider"
    SEARCH_PROVIDER = "search_provider"
    TICKET_PLATFORM_PROVIDER = "ticket_platform_provider"
    REVIEW_PLATFORM_PROVIDER = "review_platform_provider"
    WEATHER_PROVIDER = "weather_provider"
    ROUTE_PROVIDER = "route_provider"
    CRAWLER_PROVIDER = "crawler_provider"
    FALLBACK_PROVIDER = "fallback_provider"
    MODEL_PRIOR_PROVIDER = "model_prior_provider"


class S5ToolRole(str, Enum):
    PRIMARY = "primary"
    CANDIDATE = "candidate"
    FALLBACK = "fallback"
    ENRICHMENT = "enrichment"
    FORBIDDEN = "forbidden"


class S5DomainToolBinding(BaseModel):
    domain: InformationDomain
    provider_group: ProviderGroup
    tool_name: str
    role: S5ToolRole
    capabilities: list[str] = Field(default_factory=list)
    claim_types: list[str] = Field(default_factory=list)
    requires_config: bool = True
    requires_user_permission: bool = False
    limitations: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)


class S5DomainPlan(BaseModel):
    domains: list[InformationDomain] = Field(default_factory=list)
    claim_to_domains: dict[str, list[InformationDomain]] = Field(default_factory=dict)
    tool_bindings: list[S5DomainToolBinding] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def provider_groups(self) -> list[ProviderGroup]:
        seen: list[ProviderGroup] = []
        for binding in self.tool_bindings:
            if binding.provider_group not in seen:
                seen.append(binding.provider_group)
        return seen

    def candidate_tool_names(self) -> set[str]:
        allowed_roles = {
            S5ToolRole.PRIMARY,
            S5ToolRole.CANDIDATE,
            S5ToolRole.FALLBACK,
            S5ToolRole.ENRICHMENT,
        }
        return {b.tool_name for b in self.tool_bindings if b.role in allowed_roles}

    def forbidden_tool_names(self) -> set[str]:
        return {b.tool_name for b in self.tool_bindings if b.role == S5ToolRole.FORBIDDEN}

    def effective_forbidden_tool_names(self) -> set[str]:
        """Forbidden only when every domain binding for the tool is forbidden."""
        roles_by_tool: dict[str, list[S5ToolRole]] = {}
        for binding in self.tool_bindings:
            roles_by_tool.setdefault(binding.tool_name, []).append(binding.role)
        return {
            tool
            for tool, roles in roles_by_tool.items()
            if roles and all(role == S5ToolRole.FORBIDDEN for role in roles)
        }
