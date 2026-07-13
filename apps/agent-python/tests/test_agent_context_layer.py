from app.context import ContextSnapshot, SessionContext


def test_java_session_id_is_injected_into_session_context():
    session = SessionContext.from_java_payload(
        query="Plan a quiet Kyoto route",
        session_id="session-123",
        user_context={"user_id": "user-1", "preferences": ["quiet"]},
    )

    assert session.session_id == "session-123"
    assert session.query == "Plan a quiet Kyoto route"
    assert session.to_agent_user_context() == {
        "user_id": "user-1",
        "preferences": ["quiet"],
        "session_id": "session-123",
    }


def test_user_context_fields_are_preserved_without_persistence():
    raw_context = {
        "user_id": "user-2",
        "travel_date": "2026-10",
        "party": ["solo"],
        "pace": "relaxed",
        "preferences": ["museums", "low crowd"],
        "conversation_memory": {
            "last_places": ["Kyoto"],
            "last_city": "Kyoto",
            "last_query": "What about temples?",
        },
        "conversation_context": {
            "last_city": "Kyoto",
            "confirmed_preferences": ["early morning"],
        },
    }

    session = SessionContext.from_java_payload(
        query="Find something nearby",
        session_id="session-456",
        user_context=raw_context,
    )
    snapshot = ContextSnapshot.from_session(session)

    assert session.user_context["user_id"] == "user-2"
    assert session.user_context["preferences"] == ["museums", "low crowd"]
    assert snapshot.preferences.travel_date == "2026-10"
    assert snapshot.preferences.party == ["solo"]
    assert snapshot.preferences.pace == "relaxed"
    assert snapshot.conversation_memory.last_places == ["Kyoto"]
    assert snapshot.conversation_memory.last_query == "What about temples?"
    assert snapshot.conversation_context.last_city == "Kyoto"
    assert snapshot.conversation_context.confirmed_preferences == ["early morning"]


def test_missing_optional_context_produces_empty_snapshot():
    session = SessionContext.from_java_payload(
        query="Any ideas?",
        session_id=None,
        user_context=None,
    )
    snapshot = ContextSnapshot.from_session(session)

    assert session.session_id is None
    assert session.user_context == {}
    assert snapshot.preferences.preferences == []
    assert snapshot.conversation_memory.last_places == []
    assert snapshot.conversation_context.last_places == []
