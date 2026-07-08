from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    party: list[str] = Field(default_factory=list)
    pace: str | None = None
    preferences: list[str] = Field(default_factory=list)
    budget_level: str | None = None
    transport_preference: str | None = None
    constraints: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump(exclude_none=True)
