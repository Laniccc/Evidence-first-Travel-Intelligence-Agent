"""Run timeline recording."""

from typing import Any


class TraceRecorder:
    @staticmethod
    def add(state: Any, message: str) -> None:
        state.visible_trace.append(message)

    @staticmethod
    def add_many(state: Any, messages: list[str]) -> None:
        state.visible_trace.extend(messages)


__all__ = ["TraceRecorder"]
