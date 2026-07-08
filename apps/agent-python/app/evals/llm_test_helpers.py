"""Shared LLM stub for unit tests (no network)."""

from __future__ import annotations

import json
from typing import Callable


class StubLLMClient:
    """Minimal LLM client for tests — never calls the network."""

    def __init__(
        self,
        responder: Callable[[str, str], str] | None = None,
        *,
        responses: list[str | BaseException] | None = None,
    ) -> None:
        self._responder = responder or self._default_responder
        self._responses = list(responses) if responses is not None else None
        self._call_count = 0

    def _should_use_anthropic(self) -> bool:
        return True

    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 1200,
        *,
        json_only: bool = False,
    ) -> str:
        _ = (max_tokens, json_only)
        if self._responses is not None:
            idx = min(self._call_count, len(self._responses) - 1)
            self._call_count += 1
            item = self._responses[idx]
            if isinstance(item, BaseException):
                raise item
            return str(item)
        return self._responder(system, user)

    @staticmethod
    def _default_responder(system: str, user: str) -> str:
        if "search tasks" in system.lower() or "keyword search" in system.lower() or "refine" in system.lower():
            try:
                payload = json.loads(user)
            except json.JSONDecodeError:
                payload = {}
            planner_input = payload.get("planner_input")
            if isinstance(planner_input, dict):
                payload = planner_input
            raw = payload.get("raw_query") or "查询"
            entities = payload.get("entities") or {}
            places = entities.get("places") or []
            place = places[0] if places else "目的地"
            return json.dumps(
                {
                    "tasks": [
                        {
                            "anchor_keywords": [place, raw[:6]],
                            "search_query": raw,
                            "rationale": "test stub",
                            "preferred_tool": "search_mcp",
                        },
                        {
                            "anchor_keywords": [place, "攻略"],
                            "search_query": f"{place}攻略",
                            "rationale": "test stub",
                            "preferred_tool": "search_mcp",
                        },
                    ]
                },
                ensure_ascii=False,
            )
        return user


def duku_search_tasks_json() -> str:
    return json.dumps(
        {
            "tasks": [
                {
                    "anchor_keywords": ["独库公路", "开放"],
                    "search_query": "独库公路什么时候开放",
                    "rationale": "road opening",
                    "preferred_tool": "search_mcp",
                },
                {
                    "anchor_keywords": ["独库公路", "新疆"],
                    "search_query": "新疆独库公路开放月份",
                    "rationale": "regional official",
                    "preferred_tool": "search_mcp",
                },
                {
                    "anchor_keywords": ["独库公路", "通车"],
                    "search_query": "独库公路几月通车",
                    "rationale": "seasonal",
                    "preferred_tool": "search_mcp",
                },
            ]
        },
        ensure_ascii=False,
    )
