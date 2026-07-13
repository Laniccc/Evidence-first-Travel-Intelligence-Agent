"""Public API contracts for Java and frontend integration."""

from app.contracts.errors import ErrorResponse
from app.contracts.request import AgentQueryRequest, TravelQueryRequest
from app.contracts.response import AgentHealthResponse, AgentQueryResponse, TravelQueryResponse

__all__ = [
    "AgentHealthResponse",
    "AgentQueryRequest",
    "AgentQueryResponse",
    "ErrorResponse",
    "TravelQueryRequest",
    "TravelQueryResponse",
]
