"""Failure reason taxonomy for Agent runs."""

from enum import Enum

from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    CONFIGURATION = "configuration"
    POLICY = "policy"
    TOOL = "tool"
    LLM = "llm"
    EVIDENCE = "evidence"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class FailureReason(BaseModel):
    category: FailureCategory = FailureCategory.UNKNOWN
    code: str
    message: str
    recoverable: bool = True
    details: dict = Field(default_factory=dict)
