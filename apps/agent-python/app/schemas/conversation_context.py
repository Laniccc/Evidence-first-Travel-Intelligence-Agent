from pydantic import BaseModel, Field

from app.schemas.place_context import PlaceContext
from app.schemas.user_profile import UserProfile


class ConversationContext(BaseModel):
    """Session-scoped context for reference resolution — not long-term memory."""

    last_places: list[PlaceContext] = Field(default_factory=list)
    last_city: str | None = None
    last_country: str | None = None
    last_travel_date: str | None = None
    last_user_profile: UserProfile | None = None
    last_itinerary: dict | None = None
    last_task_type: str | None = None
    confirmed_preferences: list[str] = Field(default_factory=list)
    unresolved_references: list[str] = Field(default_factory=list)
    recent_turns_summary: str | None = None
