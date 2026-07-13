"""Deprecated synchronous composer surface retained outside orchestration."""

from __future__ import annotations

from typing import Any


class ComposerSubagent:
    """Legacy sync facade; the S8 pipeline uses ``AnswerComposerAgent`` instead."""

    @staticmethod
    def compose(state: Any, arguments: dict) -> str:
        raise RuntimeError(
            "ComposerSubagent is deprecated; use AnswerComposerAgent.compose via S8 answer_composition state."
        )
