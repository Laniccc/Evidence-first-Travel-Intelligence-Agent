"""Java Tool Gateway integration facade."""

from app.integrations.java_gateway.config import ToolGatewayConfig, get_tool_gateway_config
from app.integrations.java_gateway.converters import evidence_list_from_gateway, tool_trace_from_gateway
from app.integrations.java_gateway.integration import install_java_tool_gateway, try_java_tool_gateway
from app.integrations.java_gateway.java_client import (
    JavaToolGatewayClient,
    JavaToolGatewayError,
    JavaToolGatewayUnavailable,
)

__all__ = [
    "JavaToolGatewayClient",
    "JavaToolGatewayError",
    "JavaToolGatewayUnavailable",
    "ToolGatewayConfig",
    "evidence_list_from_gateway",
    "get_tool_gateway_config",
    "install_java_tool_gateway",
    "try_java_tool_gateway",
    "tool_trace_from_gateway",
]
