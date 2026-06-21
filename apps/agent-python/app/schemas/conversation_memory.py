from pydantic import BaseModel, Field


class ConversationMemory(BaseModel):
    """Session-level context for resolving deictic references (这里/那边/刚才那个)."""

    last_places: list[str] = Field(default_factory=list)
    last_query: str | None = None
    last_country: str | None = None
    last_city: str | None = None
    travel_date: str | None = None
    recent_concerns: list[str] = Field(default_factory=list)

    @classmethod
    def from_user_context(cls, user_context: dict | None) -> "ConversationMemory":
        if not user_context:
            return cls()
        raw = user_context.get("conversation_memory") or {}
        if isinstance(raw, ConversationMemory):
            return raw
        return cls.model_validate(raw)

    def with_update(self, places: list[str], query: str, country: str | None, city: str | None) -> "ConversationMemory":
        return self.model_copy(
            update={
                "last_places": places or self.last_places,
                "last_query": query,
                "last_country": country or self.last_country,
                "last_city": city or self.last_city,
            }
        )
