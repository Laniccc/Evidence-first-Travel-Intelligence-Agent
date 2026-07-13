"""Runtime retry policy for tool execution."""

from pydantic import BaseModel, Field


class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=2, ge=1)
    retryable_errors: tuple[str, ...] = ("timeout", "rate_limit", "temporary_unavailable")

    def should_retry(self, error_code: str | None, attempt: int) -> bool:
        return bool(error_code and error_code in self.retryable_errors and attempt < self.max_attempts)
