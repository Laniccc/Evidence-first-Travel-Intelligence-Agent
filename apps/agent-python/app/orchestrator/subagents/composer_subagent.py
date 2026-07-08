"""Deprecated: use AnswerComposerAgent (async) on the S8 main path."""

from app.schemas.user_query import TravelAgentState


class ComposerSubagent:
    """Legacy sync wrapper — not used by the main pipeline."""

    @staticmethod
    def compose(state: TravelAgentState, arguments: dict) -> str:
        raise RuntimeError(
            "ComposerSubagent is deprecated; use AnswerComposerAgent.compose via S8 answer_composition state."
        )
