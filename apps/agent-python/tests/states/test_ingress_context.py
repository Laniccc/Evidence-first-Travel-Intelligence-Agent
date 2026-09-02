import pytest

from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.context_loading import ContextLoadingHandler
from app.orchestration.states.ingress import InMemoryIdempotencyStore, IngressHandler


def state_context(query: str = "故宫开放时间", **updates) -> StateContext:
    values = {
        "run_id": "run-1",
        "session_id": "session-1",
        "query_id": "query-1",
        "raw_query": query,
        "user_context": {"preferences": ["无障碍"]},
    }
    values.update(updates)
    return StateContext(**values)


@pytest.mark.asyncio
async def test_ingress_rejects_blank_query_as_safe_failure():
    result = await IngressHandler().run(state_context("   "))

    assert result.next_state is AgentState.SAFE_FAILURE
    assert result.output["failure_code"] == "empty_query"


@pytest.mark.asyncio
async def test_ingress_idempotency_hit_returns_cached_delivery_without_new_claim():
    store = InMemoryIdempotencyStore()
    store.claim("idem-1", run_id="old-run")
    store.complete("idem-1", {"answer": "cached"})
    context = state_context(idempotency_key="idem-1")

    result = await IngressHandler(idempotency_store=store).run(context)

    assert result.next_state is AgentState.DELIVER
    assert result.output["idempotency_status"] == "replayed"
    assert result.output["cached_response"] == {"answer": "cached"}
    assert store.claim_count == 1


class FailingHistoryLoader:
    def load(self, session_id: str):
        raise ConnectionError("history unavailable")


@pytest.mark.asyncio
async def test_context_preserves_session_and_recovers_when_history_fails():
    context = state_context()

    result = await ContextLoadingHandler(history_loader=FailingHistoryLoader()).run(context)

    assert result.status == "recovered"
    assert result.next_state is AgentState.UNDERSTAND
    assert result.recovery.strategy == "history_unavailable"
    assert result.output["snapshot"]["session"]["session_id"] == "session-1"
    assert result.output["snapshot"]["session"]["user_context"]["preferences"] == ["无障碍"]
