from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    name: str
    description: str
    capabilities: list[str] = Field(default_factory=list)
    source_type: str | None = None
    requires_api_key: bool = False
    configured: bool = True
    limitations: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    parameters_hint: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    satisfies_needs: list[str] = Field(default_factory=list)
    call_order_hint: str = ""


class ToolWhitelist(BaseModel):
    state_name: str
    allowed_tools: list[ToolDescriptor]
    blocked_tools: list[str] = Field(default_factory=list)
    reason_by_tool: dict[str, str] = Field(default_factory=dict)
    policy_notes: list[str] = Field(default_factory=list)

    def allowed_tool_names(self) -> list[str]:
        return [tool.name for tool in self.allowed_tools if tool.configured]

    def is_allowed(self, tool_name: str) -> bool:
        return any(t.name == tool_name and t.configured for t in self.allowed_tools)

    def get_descriptor(self, tool_name: str) -> ToolDescriptor | None:
        for tool in self.allowed_tools:
            if tool.name == tool_name:
                return tool
        return None
