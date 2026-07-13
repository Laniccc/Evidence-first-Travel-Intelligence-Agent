"""User preference profile for one Agent run."""

from typing import Any

from pydantic import BaseModel, Field


class PreferenceProfile(BaseModel):
    travel_date: str | None = None
    party: list[str] = Field(default_factory=list)
    pace: str | None = None
    transport_preference: str | None = None
    budget_level: str | None = None
    preferences: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    start_location: str | None = None
    location_usage_allowed: bool = False

    @classmethod
    def from_user_context(cls, user_context: dict[str, Any] | None) -> "PreferenceProfile":
        raw = dict(user_context or {})
        return cls(
            travel_date=raw.get("travel_date"),
            party=list(raw.get("party") or []),
            pace=raw.get("pace"),
            transport_preference=raw.get("transport_preference"),
            budget_level=raw.get("budget_level"),
            preferences=list(raw.get("preferences") or []),
            constraints=list(raw.get("constraints") or []),
            start_location=raw.get("start_location"),
            location_usage_allowed=bool(raw.get("location_usage_allowed", False)),
        )
