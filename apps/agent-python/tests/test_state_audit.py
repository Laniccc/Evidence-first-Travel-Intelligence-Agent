from app.orchestration.state_audit import InMemoryStateAuditStore, StateAuditEvent
from app.orchestration.state_contracts import AgentState, StateContext


def test_audit_event_contains_references_and_digests_not_raw_payload():
    context = StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="secret user query",
        artifacts={"understanding": {"task": "fact_query"}},
    )

    event = StateAuditEvent.started(context, AgentState.UNDERSTAND, attempt=1)
    dumped = event.model_dump(mode="json")

    assert dumped["run_id"] == "run-1"
    assert dumped["state"] == "understand"
    assert dumped["input_ref"] == "run-1:understand:attempt:1:input"
    assert len(dumped["input_digest"]) == 64
    assert "secret user query" not in str(dumped)


def test_audit_store_preserves_event_order():
    context = StateContext(
        run_id="run-1",
        session_id="session-1",
        query_id="query-1",
        raw_query="query",
    )
    store = InMemoryStateAuditStore()

    store.append(StateAuditEvent.started(context, AgentState.INGRESS, attempt=1))
    store.append(
        StateAuditEvent.transition(
            context,
            from_state=AgentState.INGRESS,
            to_state=AgentState.CONTEXT,
            attempt=1,
        )
    )

    assert [event.event_type for event in store.for_run("run-1")] == [
        "phase_started",
        "transition_committed",
    ]
