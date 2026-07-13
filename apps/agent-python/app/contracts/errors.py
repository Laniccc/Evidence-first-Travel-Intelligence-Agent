"""Error response contracts for the Agent HTTP API."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    message: str
