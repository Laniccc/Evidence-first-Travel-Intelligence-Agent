"""Backward-compatible API contract imports."""

from app.contracts.request import AgentQueryRequest
from app.contracts.response import AgentQueryResponse

__all__ = ["AgentQueryRequest", "AgentQueryResponse"]
