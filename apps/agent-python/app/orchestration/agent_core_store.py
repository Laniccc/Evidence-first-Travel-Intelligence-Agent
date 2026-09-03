"""SQLite persistence for runtime audit, inspect and artifact replay."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.orchestration.agent_core_models import (
    PhaseEventRecord,
    RunInspection,
    RunRecord,
    utc_now_iso,
)


_RUN_STORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS run (
    run_id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    query_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    current_state TEXT NOT NULL,
    replay_of_run_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_query ON run(query_id, created_at DESC);
CREATE TABLE IF NOT EXISTS phase_event (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    state TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    output_json TEXT NOT NULL DEFAULT '{}',
    failure_code TEXT,
    recovery_strategy TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_attempt (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    state TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    failure_code TEXT,
    duration_ms REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_record (
    run_id TEXT NOT NULL REFERENCES run(run_id),
    evidence_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS answer_claim (
    run_id TEXT NOT NULL REFERENCES run(run_id),
    claim_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, claim_id)
);
CREATE TABLE IF NOT EXISTS citation_decision (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES run(run_id),
    claim_id TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_metric (
    run_id TEXT NOT NULL REFERENCES run(run_id),
    name TEXT NOT NULL,
    value REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, name)
);
"""


class SQLiteRunStore:
    """Small append-oriented store for runtime audit and deterministic replay."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_RUN_STORE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def start_run(
        self,
        *,
        run_id: str,
        query_id: str,
        session_id: str,
        query: str,
        replay_of_run_id: str | None = None,
        current_state: str = "ingress",
    ) -> RunRecord:
        now = utc_now_iso()
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run(
                    run_id, query_id, session_id, query_digest, status,
                    current_state, replay_of_run_id, created_at
                ) VALUES (?, ?, ?, ?, 'running', ?, ?, ?)
                """,
                (run_id, query_id, session_id, digest, current_state, replay_of_run_id, now),
            )
            connection.commit()
        return self.get_run(run_id)

    def finish_run(self, run_id: str, *, status: str, current_state: str) -> RunRecord:
        with self._connect() as connection:
            connection.execute(
                "UPDATE run SET status = ?, current_state = ?, completed_at = ? WHERE run_id = ?",
                (status, current_state, utc_now_iso(), run_id),
            )
            connection.commit()
        return self.get_run(run_id)

    def append_phase_event(
        self,
        *,
        run_id: str,
        state: str,
        status: str,
        attempt: int,
        output: dict[str, Any] | None = None,
        failure_code: str | None = None,
        recovery_strategy: str | None = None,
    ) -> PhaseEventRecord:
        now = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO phase_event(
                    run_id, state, status, attempt, output_json,
                    failure_code, recovery_strategy, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    state,
                    status,
                    attempt,
                    json.dumps(output or {}, ensure_ascii=False, default=str),
                    failure_code,
                    recovery_strategy,
                    now,
                ),
            )
            connection.execute(
                "UPDATE run SET current_state = ? WHERE run_id = ?", (state, run_id)
            )
            connection.commit()
            event_id = int(cursor.lastrowid)
        return PhaseEventRecord(
            event_id=event_id,
            run_id=run_id,
            state=state,
            status=status,
            attempt=attempt,
            output=output or {},
            failure_code=failure_code,
            recovery_strategy=recovery_strategy,
            created_at=now,
        )

    def record_execution_attempt(
        self,
        *,
        run_id: str,
        state: str,
        attempt: int,
        status: str,
        failure_code: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO execution_attempt(
                    run_id, state, attempt, status, failure_code, duration_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, state, attempt, status, failure_code, duration_ms, utc_now_iso()),
            )
            connection.commit()

    def record_evidence(self, *, run_id: str, evidence_id: str, payload: dict) -> None:
        self._upsert_payload("evidence_record", "evidence_id", run_id, evidence_id, payload)

    def record_answer_claim(self, *, run_id: str, claim_id: str, payload: dict) -> None:
        self._upsert_payload("answer_claim", "claim_id", run_id, claim_id, payload)

    def _upsert_payload(
        self, table: str, key_column: str, run_id: str, key: str, payload: dict
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {table}(run_id, {key_column}, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, {key_column}) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (run_id, key, json.dumps(payload, ensure_ascii=False, default=str), utc_now_iso()),
            )
            connection.commit()

    def record_citation_decision(
        self, *, run_id: str, claim_id: str, status: str, reason: str
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO citation_decision(run_id, claim_id, status, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, claim_id, status, reason, utc_now_iso()),
            )
            connection.commit()

    def record_metric(self, *, run_id: str, name: str, value: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_metric(run_id, name, value, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id, name) DO UPDATE SET value = excluded.value
                """,
                (run_id, name, value, utc_now_iso()),
            )
            connection.commit()

    def get_run(self, run_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM run WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown run: {run_id}")
        return RunRecord.model_validate(dict(row))

    def latest_run_for_query(self, query_id: str) -> RunRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM run WHERE query_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (query_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown query: {query_id}")
        return RunRecord.model_validate(dict(row))

    def phase_events(self, run_id: str) -> list[PhaseEventRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM phase_event WHERE run_id = ? ORDER BY event_id", (run_id,)
            ).fetchall()
        return [
            PhaseEventRecord(
                event_id=row["event_id"],
                run_id=row["run_id"],
                state=row["state"],
                status=row["status"],
                attempt=row["attempt"],
                output=json.loads(row["output_json"]),
                failure_code=row["failure_code"],
                recovery_strategy=row["recovery_strategy"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def latest_state_output(self, run_id: str, state: str) -> dict[str, Any]:
        events = [item for item in self.phase_events(run_id) if item.state == state]
        if not events:
            raise KeyError(f"run {run_id} has no output for state {state}")
        return events[-1].output

    def inspect(self, query_id: str) -> RunInspection:
        run = self.latest_run_for_query(query_id)
        with self._connect() as connection:
            attempts = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM execution_attempt WHERE run_id = ? ORDER BY attempt_id",
                    (run.run_id,),
                ).fetchall()
            ]
            evidence = self._payload_rows(connection, "evidence_record", run.run_id)
            claims = self._payload_rows(connection, "answer_claim", run.run_id)
            citations = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM citation_decision WHERE run_id = ? ORDER BY decision_id",
                    (run.run_id,),
                ).fetchall()
            ]
            metrics = {
                row["name"]: row["value"]
                for row in connection.execute(
                    "SELECT name, value FROM run_metric WHERE run_id = ?", (run.run_id,)
                ).fetchall()
            }
        return RunInspection(
            run=run,
            timeline=self.phase_events(run.run_id),
            execution_attempts=attempts,
            evidence=evidence,
            answer_claims=claims,
            citation_decisions=citations,
            metrics=metrics,
        )

    @staticmethod
    def _payload_rows(connection, table: str, run_id: str) -> list[dict[str, Any]]:
        return [
            json.loads(row["payload_json"])
            for row in connection.execute(
                f"SELECT payload_json FROM {table} WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            ).fetchall()
        ]


__all__ = ["SQLiteRunStore"]
