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


class FailureClass(str, Enum):
    """Operational failure classes shared by all explicit Agent states."""

    VALIDATION = "validation"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    EMPTY_RESULT = "empty_result"
    PARSE_ERROR = "parse_error"
    POLICY_DENIED = "policy_denied"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    ILLEGAL_TRANSITION = "illegal_transition"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERNAL = "internal"


class FailureReason(BaseModel):
    category: FailureCategory = FailureCategory.UNKNOWN
    code: str
    message: str
    recoverable: bool = True
    details: dict = Field(default_factory=dict)
