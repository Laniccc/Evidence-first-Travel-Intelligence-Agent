"""Inbound user context payload normalization."""

from typing import Any

from pydantic import BaseModel, Field


class UserContextPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, user_context: dict | None) -> "UserContextPayload":
        return cls(values=dict(user_context or {}))

    def with_session_id(self, session_id: str | None) -> dict[str, Any]:
        values = dict(self.values)
        if session_id and "session_id" not in values:
            values["session_id"] = session_id
        return values
