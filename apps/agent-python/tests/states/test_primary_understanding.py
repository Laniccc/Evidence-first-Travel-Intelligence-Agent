import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.context.conversation_context import ConversationContext
from app.governance.failure_reason import FailureClass
from app.integrations.llm.client import SingleAttemptLLMClient, ModelTransportError
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.llm_understanding import UnderstandingHandler
from app.understanding.normalized_user_request import NormalizedUserRequest
from app.understanding.primary_understanding import PrimaryUnderstandingAdapter


PAYLOAD = json.dumps({
    "task_type": "fact_query", "entities": [{"name": "故宫"}],
    "rewritten_query": "故宫开放时间", "fact_types": ["opening_hours"],
    "requested_as_of": "2026-09-06T09:00:00+08:00",
    "constraints": {"constraints": ["需要轮椅通道"]},
}, ensure_ascii=False)


class FakeModel:
    model = "fake-model"

    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.calls = []

    async def complete(self, *, system, user, max_tokens):
        self.calls.append(json.loads(user))
        value = next(self.outputs)
        if isinstance(value, BaseException):
            raise value
        return value


def context():
    return StateContext(run_id="r", session_id="s", query_id="q", raw_query="故宫几点开门")


def fallback(*_):
    return NormalizedUserRequest.model_validate({
        "raw_query": "故宫几点开门", "rewritten_query": "故宫 开放时间",
        "task_family": "fact_lookup",
        "entities": [{"text": "故宫", "entity_type": "attraction"}],
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [PAYLOAD, "{invalid", PAYLOAD.replace('"fact_query"', '"planning"')])
async def test_model_success_or_single_schema_repair_preserves_intent(first):
    model = FakeModel(first, PAYLOAD)
    handler = UnderstandingHandler(primary=PrimaryUnderstandingAdapter(model))
    result = await handler.run(context())
    repaired = first != PAYLOAD
    assert len(model.calls) == (2 if repaired else 1)
    assert model.calls[-1]["repair"] is repaired
    assert result.output["understanding_path"] == ("repair" if repaired else "model")
    request = result.output["normalized_request"]
    assert request["time_scope"]["reference_date"] == "2026-09-06T09:00:00+08:00"
    assert request["user_constraints"]["constraints"] == ["需要轮椅通道"]
    metadata = result.output["understanding_versions"]
    assert metadata["model"] == "fake-model"
    assert metadata["schema"] and metadata["prompt"]


@pytest.mark.asyncio
async def test_two_parse_errors_use_rule_and_audit_sanitized_failure():
    model = FakeModel("secret invalid", "secret invalid")
    result = await UnderstandingHandler(
        primary=PrimaryUnderstandingAdapter(model), rule_fallback=fallback,
    ).run(context())
    assert len(model.calls) == 2
    assert result.output["understanding_path"] == "rule"
    assert result.recovery.strategy == "rule_fallback"
    assert result.output["understanding_failures"][0]["code"] == "llm_schema_invalid"
    assert "secret" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_authentication_failure_is_not_schema_repaired():
    model = FakeModel(ModelTransportError("llm_auth_failed"))
    result = await UnderstandingHandler(
        primary=PrimaryUnderstandingAdapter(model), rule_fallback=fallback,
    ).run(context())
    assert len(model.calls) == 1
    assert result.output["understanding_attempts"] == ["model", "rule"]
    assert result.recovery.recovered_from is FailureClass.POLICY_DENIED


@pytest.mark.asyncio
async def test_insufficient_fallback_clarifies():
    model = FakeModel("{", "{")
    result = await UnderstandingHandler(
        primary=PrimaryUnderstandingAdapter(model),
        rule_fallback=lambda *_: NormalizedUserRequest(raw_query="那里", rewritten_query="那里"),
    ).run(context())
    assert result.next_state is AgentState.CLARIFICATION
    assert result.output["understanding_path"] == "clarification"
    assert result.output["question"]


@pytest.mark.asyncio
async def test_timeout_cancels_transport_and_does_not_retry():
    cancelled = asyncio.Event()

    class SlowModel:
        async def complete(self, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    result = await UnderstandingHandler(
        primary=PrimaryUnderstandingAdapter(SlowModel()), rule_fallback=fallback,
        primary_timeout_seconds=0.02,
    ).run(context())
    assert cancelled.is_set()
    assert result.output["understanding_attempts"] == ["model", "rule"]
    assert result.recovery.recovered_from is FailureClass.TIMEOUT


@pytest.mark.asyncio
async def test_parent_cancellation_propagates_without_fallback():
    entered = asyncio.Event()

    class SlowModel:
        async def complete(self, **kwargs):
            entered.set()
            await asyncio.Event().wait()

    handler = UnderstandingHandler(primary=PrimaryUnderstandingAdapter(SlowModel()),
                                   rule_fallback=lambda *_: pytest.fail("cancel must not fallback"))
    run = asyncio.create_task(handler.run(context()))
    await entered.wait()
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [
    (401, "llm_auth_failed"), (429, "llm_rate_limited"), (500, "llm_unavailable"),
])
async def test_async_sdk_has_no_hidden_retry_or_error_body_leak(status, code):
    calls = []

    async def respond(request):
        calls.append(request)
        return httpx.Response(status, json={"type": "error", "error": {
            "type": "api_error", "message": "secret-provider-body"}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    settings = Settings(_env_file=None, anthropic_api_key="test-key", deepseek_api_key=None)
    client = SingleAttemptLLMClient(settings, http_client=http)
    try:
        with pytest.raises(ModelTransportError) as raised:
            await client.complete(system="prompt-secret", user="query", max_tokens=128)
        assert raised.value.code == code
        assert "secret" not in str(raised.value)
        assert len(calls) == 1
    finally:
        await client.aclose()
    assert http.is_closed


@pytest.mark.asyncio
async def test_adapter_context_is_bounded_and_excludes_unrelated_data():
    model = FakeModel(PAYLOAD)
    await PrimaryUnderstandingAdapter(model).normalize(
        "故宫几点开门", ConversationContext(recent_turns_summary="private secret"),
        repair=False,
    )
    assert "private secret" not in json.dumps(model.calls)


def test_offline_config_needs_no_credentials_and_rejects_invalid_deadline():
    assert Settings(_env_file=None, anthropic_api_key=None, deepseek_api_key=None).agent_runtime_profile == "offline"
    with pytest.raises(ValueError):
        Settings(_env_file=None, understanding_timeout_seconds=0)
