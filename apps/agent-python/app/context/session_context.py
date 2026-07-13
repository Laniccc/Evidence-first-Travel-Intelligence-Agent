"""Session-scoped context for one Agent run."""

from typing import Any

from pydantic import BaseModel, Field

from app.context.conversation_context import ConversationContext, ConversationMemory
from app.context.preference_profile import PreferenceProfile
from app.context.user_context import UserContextPayload


class SessionContext(BaseModel):
    query: str
    session_id: str | None = None
    user_context: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_java_payload(
        cls,
        query: str,
        session_id: str | None,
        user_context: dict | None,
    ) -> "SessionContext":
        payload = UserContextPayload.from_raw(user_context)
        merged_context = payload.with_session_id(session_id or payload.values.get("session_id"))
        return cls(
            query=query,
            session_id=session_id or merged_context.get("session_id"),
            user_context=merged_context,
        )

    def to_agent_user_context(self) -> dict[str, Any]:
        return dict(self.user_context)


class ContextSnapshot(BaseModel):
    session: SessionContext
    preferences: PreferenceProfile = Field(default_factory=PreferenceProfile)
    conversation_memory: ConversationMemory = Field(default_factory=ConversationMemory)
    conversation_context: ConversationContext = Field(default_factory=ConversationContext)

    @classmethod
    def from_session(cls, session: SessionContext) -> "ContextSnapshot":
        user_context = dict(session.user_context)
        return cls(
            session=session,
            preferences=PreferenceProfile.from_user_context(user_context),
            conversation_memory=ConversationMemory.from_user_context(user_context),
            conversation_context=ConversationContext.model_validate(
                user_context.get("conversation_context") or {}
            ),
        )
