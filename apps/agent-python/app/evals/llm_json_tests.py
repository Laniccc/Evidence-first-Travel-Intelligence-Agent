import json

import pytest

from app.utils.llm_json import normalize_llm_json_text, parse_llm_json


def test_normalize_strips_markdown_fence():
    raw = '```json\n{"headline": "hi", "conclusion": "ok"}\n```'
    assert parse_llm_json(raw)["headline"] == "hi"


def test_normalize_extracts_object_from_prose():
    raw = 'Here is the draft:\n{"conclusion": "test", "answer_text": "body"}'
    data = parse_llm_json(raw)
    assert data["conclusion"] == "test"


def test_repair_truncated_at_eof():
    raw = (
        '{\n'
        '  "headline": "关于 Sapporo",\n'
        '  "conclusion": "1–2 月看雪",\n'
        '  "answer_text": "多行答案未闭合'
    )
    data = parse_llm_json(raw)
    assert data["headline"] == "关于 Sapporo"
    assert "1" in data["conclusion"]


def test_escape_multiline_string_values():
    raw = (
        '{\n'
        '  "conclusion": "line1",\n'
        '  "answer_text": "第一行\n第二行"\n'
        "}"
    )
    data = parse_llm_json(raw)
    assert "第一行" in data["answer_text"]
    assert "第二行" in data["answer_text"]


def test_normalize_llm_json_text_balanced_only():
    text = 'prefix {"a": 1, "b": {"c": 2}} trailing'
    normalized = normalize_llm_json_text(text)
    assert normalized == '{"a": 1, "b": {"c": 2}}'
    assert parse_llm_json(text)["b"]["c"] == 2


def test_parse_raises_on_non_object():
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("not json at all")
