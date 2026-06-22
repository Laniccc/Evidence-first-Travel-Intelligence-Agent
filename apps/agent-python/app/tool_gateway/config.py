import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolGatewayConfig:
    base_url: str
    use_java_tool_gateway: bool


def get_tool_gateway_config() -> ToolGatewayConfig:
    base = os.getenv("TOOL_GATEWAY_BASE_URL", "http://localhost:8082").rstrip("/")
    enabled = os.getenv("USE_JAVA_TOOL_GATEWAY", "false").lower() in {"1", "true", "yes"}
    return ToolGatewayConfig(base_url=base, use_java_tool_gateway=enabled)
