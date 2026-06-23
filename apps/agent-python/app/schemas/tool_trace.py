from pydantic import BaseModel, Field


class ToolTrace(BaseModel):
    tool_name: str
    input: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    status: str = "ok"
    error: str | None = None
    fallback_used: bool = False
    cache_hit: bool = False
    requested_by_state: str | None = None
    selected_by_llm: bool = False
    whitelist_checked: bool = False
    provider: str | None = None
    configured: bool | None = None
    crawler_command: str | None = None
    crawler_workdir: str | None = None
    snapshot_saved_count: int | None = None
    output_parse_status: str | None = None
