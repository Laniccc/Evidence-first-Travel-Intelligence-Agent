"""Ingress validation and run idempotency boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.orchestration.state_contracts import AgentState, StateContext, StateResult


@dataclass(frozen=True)
class IdempotencyRecord:
    run_id: str
    response: dict[str, Any] | None = None


class IdempotencyStore(Protocol):
    def get(self, key: str) -> IdempotencyRecord | None: ...

    def claim(self, key: str, *, run_id: str) -> None: ...


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, IdempotencyRecord] = {}
        self.claim_count = 0

    def get(self, key: str) -> IdempotencyRecord | None:
        return self._records.get(key)

    def claim(self, key: str, *, run_id: str) -> None:
        if key in self._records:
            return
        self._records[key] = IdempotencyRecord(run_id=run_id)
        self.claim_count += 1

    def complete(self, key: str, response: dict[str, Any]) -> None:
        record = self._records[key]
        self._records[key] = IdempotencyRecord(run_id=record.run_id, response=dict(response))


class IngressHandler:
    def __init__(self, *, idempotency_store: IdempotencyStore | None = None) -> None:
        self._idempotency = idempotency_store

    async def run(self, context: StateContext) -> StateResult:
        query = context.raw_query.strip()
        if not query:
            return StateResult.succeeded(
                next_state=AgentState.SAFE_FAILURE,
                output={
                    "failure_code": "empty_query",
                    "message": "请输入要查询的景点问题。",
                },
            )

        key = context.idempotency_key
        if key and self._idempotency:
            record = self._idempotency.get(key)
            if record and record.response is not None:
                return StateResult.succeeded(
                    next_state=AgentState.DELIVER,
                    output={
                        "idempotency_status": "replayed",
                        "original_run_id": record.run_id,
                        "cached_response": record.response,
                    },
                )
            if record:
                return StateResult.succeeded(
                    next_state=AgentState.SAFE_FAILURE,
                    output={
                        "failure_code": "duplicate_in_progress",
                        "original_run_id": record.run_id,
                    },
                )
            self._idempotency.claim(key, run_id=context.run_id)

        return StateResult.succeeded(
            next_state=AgentState.CONTEXT,
            output={
                "query_length": len(query),
                "session_id": context.session_id,
                "idempotency_status": "claimed" if key else "not_requested",
            },
        )


__all__ = ["IdempotencyRecord", "IdempotencyStore", "InMemoryIdempotencyStore", "IngressHandler"]
