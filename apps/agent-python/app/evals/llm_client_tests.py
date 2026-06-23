"""LLM client behavior tests (no network)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm_client import LLMClient


def test_extract_message_text_reads_text_blocks():
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text='{"ok": true}'),
        ],
        stop_reason="end_turn",
    )
    text, stop_reason, blocks = LLMClient._extract_message_text(message)
    assert text == '{"ok": true}'
    assert stop_reason == "end_turn"
    assert blocks == ["text"]


def test_extract_message_text_skips_empty_blocks():
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=""),
            SimpleNamespace(type="text", text="hello"),
        ],
        stop_reason="end_turn",
    )
    text, _, _ = LLMClient._extract_message_text(message)
    assert text == "hello"


@pytest.mark.asyncio
async def test_complete_retries_on_empty_response(monkeypatch):
    calls: list[int] = []

    def _fake_create(_system: str, _user: str, max_tokens: int):
        calls.append(max_tokens)
        if len(calls) == 1:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="")],
                stop_reason="max_tokens",
                usage=None,
            )
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"tasks":[]}')],
            stop_reason="end_turn",
            usage=None,
        )

    client = LLMClient.__new__(LLMClient)
    client.settings = SimpleNamespace(
        llm_empty_response_retries=3,
        llm_max_output_tokens=4096,
        llm_json_min_tokens=1536,
        llm_disable_thinking=True,
        anthropic_base_url="https://api.deepseek.com/anthropic",
        llm_model=lambda: "test-model",
    )
    client._client = object()

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.llm_client.asyncio.sleep", _no_sleep)
    monkeypatch.setattr(client, "_create_message", _fake_create)

    text = await client.complete("sys", "user", max_tokens=512, json_only=True)
    assert text == '{"tasks":[]}'
    assert len(calls) == 2
    assert calls[1] >= calls[0]


def test_create_message_disables_thinking_on_deepseek():
    client = LLMClient.__new__(LLMClient)
    client.settings = SimpleNamespace(
        anthropic_base_url="https://api.deepseek.com/anthropic",
        llm_disable_thinking=True,
        llm_model=lambda: "deepseek-v4-flash",
    )
    captured: dict = {}

    def _fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content=[], stop_reason="end_turn")

    client._client = SimpleNamespace(messages=SimpleNamespace(create=_fake_create))
    client._create_message("sys", "user", 512)
    assert captured.get("thinking") == {"type": "disabled"}
