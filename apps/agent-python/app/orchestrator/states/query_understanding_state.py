"""Backward-compatible alias — main pipeline uses LLMUnderstandingState."""

from app.orchestrator.states.llm_understanding_state import LLMUnderstandingState as QueryUnderstandingPromptState

__all__ = ["QueryUnderstandingPromptState"]
