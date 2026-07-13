"""Backward-compatible alias: main pipeline uses LLMUnderstandingState."""

from app.orchestration.states.llm_understanding import LLMUnderstandingState as QueryUnderstandingPromptState

__all__ = ["QueryUnderstandingPromptState"]
