"""Conversation and memory context owned by the Agent context layer."""

from __future__ import annotations

import importlib
from typing import Any, Callable

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


class ConversationMemory(BaseModel):
    """Session-level memory for resolving references across turns."""

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

    def with_update(
        self,
        places: list[str],
        query: str,
        country: str | None,
        city: str | None,
    ) -> "ConversationMemory":
        return self.model_copy(
            update={
                "last_places": places or self.last_places,
                "last_query": query,
                "last_country": country or self.last_country,
                "last_city": city or self.last_city,
            }
        )


class ConversationContext(BaseModel):
    """Session-scoped context for reference resolution, not durable memory."""

    last_places: list[Any] = Field(default_factory=list)
    last_city: str | None = None
    last_country: str | None = None
    last_travel_date: str | None = None
    last_user_profile: UserProfile | None = None
    last_itinerary: dict | None = None
    last_task_type: str | None = None
    confirmed_preferences: list[str] = Field(default_factory=list)
    unresolved_references: list[str] = Field(default_factory=list)
    recent_turns_summary: str | None = None


class ConversationContextBuilder:
    def __init__(self, place_resolver: Callable[[str], Any] | None = None) -> None:
        self._place_resolver = place_resolver
        self._place_catalog: Any | None = None

    def build(
        self,
        state: Any,
        user_context: dict | None = None,
        user_ctx: Any | None = None,
    ) -> ConversationContext:
        del state
        raw_ctx = (user_context or {}).get("conversation_context") or {}
        memory = ConversationMemory.from_user_context(user_context)

        last_places: list[Any] = []
        if isinstance(raw_ctx, dict) and raw_ctx.get("last_places"):
            for item in raw_ctx["last_places"]:
                if isinstance(item, str):
                    last_places.append(self._place_from_name(item))
                else:
                    last_places.append(item)
        elif memory.last_places:
            last_places = [self._place_from_name(place) for place in memory.last_places]

        profile = self._profile_from_context(raw_ctx, user_ctx)
        return ConversationContext(
            last_places=last_places,
            last_city=(raw_ctx.get("last_city") if isinstance(raw_ctx, dict) else None) or memory.last_city,
            last_country=(raw_ctx.get("last_country") if isinstance(raw_ctx, dict) else None) or memory.last_country,
            last_travel_date=(
                (raw_ctx.get("last_travel_date") if isinstance(raw_ctx, dict) else None)
                or memory.travel_date
                or (getattr(user_ctx, "travel_date", None) if user_ctx else None)
            ),
            last_user_profile=profile,
            last_itinerary=raw_ctx.get("last_itinerary") if isinstance(raw_ctx, dict) else None,
            last_task_type=raw_ctx.get("last_task_type") if isinstance(raw_ctx, dict) else None,
            confirmed_preferences=raw_ctx.get("confirmed_preferences", []) if isinstance(raw_ctx, dict) else [],
            recent_turns_summary=raw_ctx.get("recent_turns_summary") if isinstance(raw_ctx, dict) else memory.last_query,
        )

    def _profile_from_context(self, raw_ctx: Any, user_ctx: Any | None) -> UserProfile | None:
        if user_ctx and getattr(user_ctx, "party", None):
            pace = getattr(user_ctx, "pace", None)
            pace_value = getattr(pace, "value", pace)
            return UserProfile(
                party=[getattr(item, "value", item) for item in getattr(user_ctx, "party", [])],
                pace=pace_value if pace_value != "unknown" else None,
            )
        if isinstance(raw_ctx, dict) and raw_ctx.get("last_user_profile"):
            return UserProfile.model_validate(raw_ctx["last_user_profile"])
        return None

    def _place_from_name(self, name: str) -> Any:
        resolver = self._place_resolver or self._resolve_place_from_catalog
        ctx = resolver(name)
        if hasattr(ctx, "model_copy"):
            return ctx.model_copy(update={"source": "query_understanding"})
        return ctx

    def _resolve_place_from_catalog(self, name: str) -> Any:
        if self._place_catalog is None:
            module = importlib.import_module("app.integrations.catalog.place_catalog")
            self._place_catalog = module.get_place_catalog()
        return self._place_catalog.resolve_place_context(name)


__all__ = [
    "ConversationContext",
    "ConversationContextBuilder",
    "ConversationMemory",
    "UserProfile",
]
