import asyncio
import json

import pytest

from app.composition.llm_composer import BoundedLLMComposer
from app.orchestration.states.answer_composition import GroundedCompositionHandler
from app.orchestration.states.citation_guard import CitationGuardHandler
from tests.states.test_composition import context


class Model:
    def __init__(self, response):
        self.response, self.calls = response, []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


async def test_order_plan_preserves_claims_and_is_effective_after_guard():
    ctx = context()
    base = await GroundedCompositionHandler().run(ctx)
    claims = base.output["answer_claims"]
    second = {**claims[0], "claim_id": "second", "subtask_id": "sub-2"}
    model = Model(json.dumps({"claim_order": ["second", claims[0]["claim_id"]]}))
    bundle = {"query": "private query not needed", "accepted_claims": [*claims, second]}
    draft = await BoundedLLMComposer(model).compose_claims(bundle, repair=False)
    assert draft["answer_claims"] == [second, *claims]
    assert "private query" not in model.calls[0]["user"]
    assert model.calls[0]["max_tokens"] == 512
    result = await GroundedCompositionHandler(composer=BoundedLLMComposer(
        Model(json.dumps({"claim_order": [claims[0]["claim_id"]]})))).run(ctx)
    ctx.artifacts["compose"] = result.output
    guarded = await CitationGuardHandler().run(ctx)
    assert guarded.output["citation_report"]["passed"]
    assert guarded.output["supported_claims"] == claims
    assert result.output["composition_mode"] == "model"


@pytest.mark.parametrize("payload", [
    "not json", '{"claim_order":[]}', '{"claim_order":["unknown"]}',
    '{"claim_order":["sub-1:opening_hours","sub-1:opening_hours"]}',
    '{"claim_order":["sub-1:opening_hours"],"answer":"免费入园"}',
    '{"claim_order":[7]}',
])
async def test_invalid_proposals_fallback_once_without_leaking_text(payload):
    model = Model(payload)
    result = await GroundedCompositionHandler(composer=BoundedLLMComposer(model)).run(context())
    assert len(model.calls) == 1
    assert result.status == "recovered"
    assert result.output["failure_code"] == "composer_invalid_output"
    assert result.output["composition_mode"] == "deterministic_fallback"
    assert result.output["answer_claims"][0]["text"] == "故宫八点三十分开放"
    assert "免费入园" not in json.dumps(result.output, ensure_ascii=False)


async def test_timeout_fallback_is_bounded_and_cancellation_propagates():
    class Slow:
        calls = 0
        async def compose_claims(self, *args, **kwargs):
            self.calls += 1
            await asyncio.sleep(30)
    slow = Slow()
    result = await GroundedCompositionHandler(composer=slow, timeout_seconds=0.01).run(context())
    assert slow.calls == 1 and result.output["failure_code"] == "composer_timeout"
    with pytest.raises(asyncio.CancelledError):
        await GroundedCompositionHandler(composer=BoundedLLMComposer(
            Model(asyncio.CancelledError()))).run(context())


async def test_transport_failure_is_typed_and_does_not_repair():
    from app.integrations.llm.client import ModelTransportError
    model = Model(ModelTransportError("llm_rate_limited"))
    result = await GroundedCompositionHandler(composer=BoundedLLMComposer(model)).run(context())
    assert len(model.calls) == 1
    assert result.output["failure_code"] == "llm_rate_limited"
    assert result.recovery.recovered_from.value == "rate_limit"


async def test_large_input_never_reaches_model():
    model = Model("{}")
    base = await GroundedCompositionHandler().run(context())
    claim = base.output["answer_claims"][0]
    claim["text"] = "x" * 16001
    with pytest.raises(ValueError):
        await BoundedLLMComposer(model).compose_claims({"accepted_claims": [claim]}, repair=False)
    assert not model.calls


async def test_injected_draft_cannot_mutate_approved_fact_or_drop_claim():
    class Invented:
        async def compose_claims(self, bundle, **kwargs):
            return {"answer_claims": [{**bundle["accepted_claims"][0], "text": "免费入园"}],
                    "answer_text": "免费入园"}
    result = await GroundedCompositionHandler(composer=Invented()).run(context())
    assert result.output["composition_mode"] == "deterministic_fallback"
    assert result.output["failure_code"] == "composer_invalid_output"
