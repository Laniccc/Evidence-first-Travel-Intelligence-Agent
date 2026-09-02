"""Experimental in-memory Agent Core Store.

This is intentionally small: it lets the existing state machine write phase
records as a sidecar, so we can validate the Root Agent / Store projection
architecture before replacing the current S0-S10 runner.
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.orchestration.agent_core_models import (
    ArtifactRecord,
    EvidenceRecord,
    JobRecord,
    PhaseOutputRecord,
    PhaseStateRecord,
    PipelineStateProjection,
    PhaseEventRecord,
    RunInspection,
    RunRecord,
    utc_now_iso,
)
from app.orchestration._legacy_boundary import legacy_config_attr
from app.evidence.evidence_model import Evidence
from app.orchestration.travel_agent_state import TravelAgentState

get_settings = legacy_config_attr("get_settings")


_PHASE_ORDER = (
    "ingress",
    "input_contract",
    "research_plan",
    "evidence_acquisition",
    "evidence_review",
    "answer_draft",
    "citation_guard",
    "delivery",
)


@runtime_checkable
class AgentCoreStore(Protocol):
    run_id: str

    def set_phase(
        self,
        phase: str,
        status: str,
        *,
        output_refs: list[str] | None = None,
        error: str | None = None,
    ) -> PhaseStateRecord: ...

    def add_phase_output(
        self,
        phase: str,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        status: str = "draft",
        evidence_refs: list[str] | None = None,
        created_by: str = "state_machine",
    ) -> PhaseOutputRecord: ...

    def approve_phase(
        self,
        phase: str,
        *,
        output_id: str | None = None,
        approved_by: str = "root_agent",
    ) -> PhaseStateRecord: ...

    def rollback_to_phase(self, phase: str, *, reason: str) -> PhaseStateRecord: ...

    def add_job(
        self,
        *,
        tool_name: str,
        status: str = "queued",
        input: dict[str, Any] | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord: ...

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord: ...

    def upsert_evidence(
        self,
        ev: Evidence,
        *,
        usage_role: str = "context",
        strength: str = "unknown",
    ) -> EvidenceRecord: ...

    def add_artifact(
        self,
        *,
        artifact_type: str,
        payload: dict[str, Any] | None = None,
        status: str = "draft",
        cited_evidence_refs: list[str] | None = None,
    ) -> ArtifactRecord: ...

    def has_phase_output(
        self,
        phase: str,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> bool: ...

    def latest_phase_output(
        self,
        phase: str,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> PhaseOutputRecord | None: ...

    def pending_jobs(self) -> list[JobRecord]: ...

    def project(self) -> PipelineStateProjection: ...


class InMemoryAgentStore:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.phase_states: dict[str, PhaseStateRecord] = {}
        self.phase_outputs: list[PhaseOutputRecord] = []
        self.evidence_records: dict[str, EvidenceRecord] = {}
        self.artifact_records: list[ArtifactRecord] = []
        self.job_records: dict[str, JobRecord] = {}

    def set_phase(
        self,
        phase: str,
        status: str,
        *,
        output_refs: list[str] | None = None,
        error: str | None = None,
    ) -> PhaseStateRecord:
        prev = self.phase_states.get(phase)
        record = PhaseStateRecord(
            run_id=self.run_id,
            phase=phase,
            status=status,
            attempt=prev.attempt if prev else 1,
            input_refs=list(prev.input_refs if prev else []),
            output_refs=list(output_refs if output_refs is not None else (prev.output_refs if prev else [])),
            approved_by=prev.approved_by if prev else None,
            approved_at=prev.approved_at if prev else None,
            error=error,
            updated_at=utc_now_iso(),
        )
        self.phase_states[phase] = record
        return record

    def add_phase_output(
        self,
        phase: str,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        status: str = "draft",
        evidence_refs: list[str] | None = None,
        created_by: str = "state_machine",
    ) -> PhaseOutputRecord:
        output = PhaseOutputRecord(
            run_id=self.run_id,
            phase=phase,
            kind=kind,
            status=status,
            payload=payload or {},
            evidence_refs=evidence_refs or [],
            created_by=created_by,
        )
        self.phase_outputs.append(output)
        refs = list(self.phase_states.get(phase).output_refs if phase in self.phase_states else [])
        refs.append(output.id)
        self.set_phase(phase, status="succeeded" if status in {"approved", "succeeded"} else status, output_refs=refs)
        return output

    def approve_phase(
        self,
        phase: str,
        *,
        output_id: str | None = None,
        approved_by: str = "root_agent",
    ) -> PhaseStateRecord:
        output = self._select_phase_output(phase, output_id=output_id)
        output.status = "approved"
        artifact_id = output.payload.get("artifact_id") if isinstance(output.payload, dict) else None
        if artifact_id:
            for artifact in self.artifact_records:
                if artifact.id == artifact_id:
                    artifact.status = "approved"
                    break
        prev = self.phase_states.get(phase)
        refs = list(prev.output_refs if prev else [])
        if output.id not in refs:
            refs.append(output.id)
        approved_at = utc_now_iso()
        record = PhaseStateRecord(
            run_id=self.run_id,
            phase=phase,
            status="approved",
            attempt=prev.attempt if prev else 1,
            input_refs=list(prev.input_refs if prev else []),
            output_refs=refs,
            approved_by=approved_by,
            approved_at=approved_at,
            error=None,
            updated_at=approved_at,
        )
        self.phase_states[phase] = record
        return record

    def rollback_to_phase(
        self,
        phase: str,
        *,
        reason: str,
    ) -> PhaseStateRecord:
        if phase not in _PHASE_ORDER:
            raise ValueError(f"Unknown phase: {phase}")
        target_idx = _PHASE_ORDER.index(phase)
        for later in _PHASE_ORDER[target_idx + 1 :]:
            if later in self.phase_states:
                self.set_phase(later, "rolled_back", error=reason)
        prev = self.phase_states.get(phase)
        record = PhaseStateRecord(
            run_id=self.run_id,
            phase=phase,
            status="running",
            attempt=(prev.attempt + 1) if prev else 1,
            input_refs=list(prev.input_refs if prev else []),
            output_refs=list(prev.output_refs if prev else []),
            approved_by=None,
            approved_at=None,
            error=reason,
            updated_at=utc_now_iso(),
        )
        self.phase_states[phase] = record
        return record

    def add_job(
        self,
        *,
        tool_name: str,
        status: str = "queued",
        input: dict[str, Any] | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        record = JobRecord(
            run_id=self.run_id,
            tool_name=tool_name,
            status=status,
            input=input or {},
            output_ref=output_ref,
            error=error,
        )
        self.job_records[record.id] = record
        return record

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        record = self.job_records.get(job_id)
        if record is None:
            raise ValueError(f"Unknown job: {job_id}")
        if status is not None:
            record.status = status
        if output_ref is not None:
            record.output_ref = output_ref
        if error is not None:
            record.error = error
        record.updated_at = utc_now_iso()
        return record

    def upsert_evidence(self, ev: Evidence, *, usage_role: str = "context", strength: str = "unknown") -> EvidenceRecord:
        record = EvidenceRecord(
            id=ev.evidence_id,
            run_id=self.run_id,
            source_type=ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
            source_name=ev.source_name,
            source_url=ev.source_url,
            payload={
                "place_name": ev.place_name,
                "confidence": ev.confidence,
                "claims": [
                    c.model_dump(mode="json") if hasattr(c, "model_dump") else dict(c)
                    for c in (ev.claims or [])
                ],
            },
            strength=strength,
            usage_role=usage_role,
        )
        self.evidence_records[record.id] = record
        return record

    def add_artifact(
        self,
        *,
        artifact_type: str,
        payload: dict[str, Any] | None = None,
        status: str = "draft",
        cited_evidence_refs: list[str] | None = None,
    ) -> ArtifactRecord:
        artifact = ArtifactRecord(
            run_id=self.run_id,
            artifact_type=artifact_type,
            status=status,
            payload=payload or {},
            cited_evidence_refs=cited_evidence_refs or [],
        )
        self.artifact_records.append(artifact)
        return artifact

    def _select_phase_output(self, phase: str, *, output_id: str | None = None) -> PhaseOutputRecord:
        matches = [output for output in self.phase_outputs if output.phase == phase]
        if output_id is not None:
            for output in matches:
                if output.id == output_id:
                    return output
            raise ValueError(f"Unknown output for phase={phase}: {output_id}")
        if not matches:
            raise ValueError(f"No phase output to approve for phase={phase}")
        return matches[-1]

    def has_phase_output(
        self,
        phase: str,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> bool:
        return self.latest_phase_output(phase, kind=kind, status=status) is not None

    def latest_phase_output(
        self,
        phase: str,
        *,
        kind: str | None = None,
        status: str | None = None,
    ) -> PhaseOutputRecord | None:
        for output in reversed(self.phase_outputs):
            if output.phase != phase:
                continue
            if kind is not None and output.kind != kind:
                continue
            if status is not None and output.status != status:
                continue
            return output
        return None

    def pending_jobs(self) -> list[JobRecord]:
        return [
            job
            for job in self.job_records.values()
            if job.status in {"queued", "running"}
        ]

    def project(self) -> PipelineStateProjection:
        latest_outputs: dict[str, dict[str, Any]] = {}
        for output in self.phase_outputs:
            latest_outputs[output.phase] = output.model_dump(mode="json")
        latest_artifacts: dict[str, dict[str, Any]] = {}
        for artifact in self.artifact_records:
            latest_artifacts[artifact.artifact_type] = artifact.model_dump(mode="json")
        source_counts = Counter(r.source_type for r in self.evidence_records.values())
        usage_role_counts = Counter(r.usage_role for r in self.evidence_records.values())
        strength_counts = Counter(r.strength for r in self.evidence_records.values())
        job_counts = Counter(r.status for r in self.job_records.values())
        current_phase = None
        for phase in _PHASE_ORDER:
            if self.phase_states.get(phase) and self.phase_states[phase].status not in {"succeeded", "approved", "skipped"}:
                current_phase = phase
                break
        if current_phase is None:
            for phase in reversed(_PHASE_ORDER):
                if phase in self.phase_states:
                    current_phase = phase
                    break
        return PipelineStateProjection(
            run_id=self.run_id,
            current_phase=current_phase,
            phase_status={phase: self.phase_states[phase].status for phase in _PHASE_ORDER if phase in self.phase_states},
            latest_outputs=latest_outputs,
            evidence_summary=_evidence_summary_payload(
                latest_outputs,
                count=len(self.evidence_records),
                source_counts=source_counts,
                usage_role_counts=usage_role_counts,
                strength_counts=strength_counts,
            ),
            claim_decisions=_claim_decisions_payload(latest_outputs),
            gaps=_gap_payload(latest_outputs),
            latest_artifacts=latest_artifacts,
            job_status=dict(job_counts),
        )


class JsonlAgentStore(InMemoryAgentStore):
    """Append-only local Agent Core Store audit log.

    The in-memory indexes remain the live projection cache for this process;
    every write also appends a durable JSONL record for inspection and later
    replay/SQLite migration.
    """

    def __init__(self, run_id: str, path: str | Path) -> None:
        super().__init__(run_id=run_id)
        self.path = Path(path)

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "run_id": self.run_id,
            "event_type": event_type,
            "payload": payload,
            "created_at": utc_now_iso(),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def set_phase(
        self,
        phase: str,
        status: str,
        *,
        output_refs: list[str] | None = None,
        error: str | None = None,
    ) -> PhaseStateRecord:
        record = super().set_phase(phase, status, output_refs=output_refs, error=error)
        self._append_event("phase_state", record.model_dump(mode="json"))
        return record

    def add_phase_output(
        self,
        phase: str,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        status: str = "draft",
        evidence_refs: list[str] | None = None,
        created_by: str = "state_machine",
    ) -> PhaseOutputRecord:
        record = super().add_phase_output(
            phase,
            kind=kind,
            payload=payload,
            status=status,
            evidence_refs=evidence_refs,
            created_by=created_by,
        )
        self._append_event("phase_output", record.model_dump(mode="json"))
        return record

    def approve_phase(
        self,
        phase: str,
        *,
        output_id: str | None = None,
        approved_by: str = "root_agent",
    ) -> PhaseStateRecord:
        record = super().approve_phase(phase, output_id=output_id, approved_by=approved_by)
        self._append_event("phase_approval", record.model_dump(mode="json"))
        return record

    def rollback_to_phase(self, phase: str, *, reason: str) -> PhaseStateRecord:
        record = super().rollback_to_phase(phase, reason=reason)
        self._append_event(
            "phase_rollback",
            {"phase": phase, "reason": reason, "state": record.model_dump(mode="json")},
        )
        return record

    def add_job(
        self,
        *,
        tool_name: str,
        status: str = "queued",
        input: dict[str, Any] | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        record = super().add_job(
            tool_name=tool_name,
            status=status,
            input=input,
            output_ref=output_ref,
            error=error,
        )
        self._append_event("job", record.model_dump(mode="json"))
        return record

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        record = super().update_job(job_id, status=status, output_ref=output_ref, error=error)
        self._append_event("job_update", record.model_dump(mode="json"))
        return record

    def upsert_evidence(
        self,
        ev: Evidence,
        *,
        usage_role: str = "context",
        strength: str = "unknown",
    ) -> EvidenceRecord:
        record = super().upsert_evidence(ev, usage_role=usage_role, strength=strength)
        self._append_event("evidence_record", record.model_dump(mode="json"))
        return record

    def add_artifact(
        self,
        *,
        artifact_type: str,
        payload: dict[str, Any] | None = None,
        status: str = "draft",
        cited_evidence_refs: list[str] | None = None,
    ) -> ArtifactRecord:
        record = super().add_artifact(
            artifact_type=artifact_type,
            payload=payload,
            status=status,
            cited_evidence_refs=cited_evidence_refs,
        )
        self._append_event("artifact_record", record.model_dump(mode="json"))
        return record


class SQLiteAgentStore(JsonlAgentStore):
    """SQLite-backed Agent Core audit store.

    Like JsonlAgentStore, the current process keeps an in-memory projection
    cache. SQLite stores append-only events in a queryable table.
    """

    def __init__(self, run_id: str, path: str | Path) -> None:
        InMemoryAgentStore.__init__(self, run_id=run_id)
        self.path = Path(path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_core_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_core_events_run "
                "ON agent_core_events(run_id, id)"
            )

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        created_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_core_events(run_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    self.run_id,
                    event_type,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    created_at,
                ),
            )

    def events(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        target_run = run_id or self.run_id
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, event_type, payload_json, created_at
                FROM agent_core_events
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (target_run,),
            ).fetchall()
        return [
            {
                "run_id": row[0],
                "event_type": row[1],
                "payload": json.loads(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]


def ensure_agent_core_store(state: TravelAgentState) -> AgentCoreStore:
    store = getattr(state, "agent_core_store", None)
    if isinstance(store, AgentCoreStore):
        return store
    store = create_agent_core_store(run_id=state.query_id)
    state.agent_core_store = store
    return store


def create_agent_core_store(run_id: str) -> AgentCoreStore:
    try:
        settings = get_settings()
        if settings.agent_core_store_backend == "jsonl":
            return JsonlAgentStore(run_id=run_id, path=settings.agent_core_store_jsonl_path)
        if settings.agent_core_store_backend == "sqlite":
            return SQLiteAgentStore(run_id=run_id, path=settings.agent_core_store_sqlite_path)
    except Exception:
        pass
    return InMemoryAgentStore(run_id=run_id)


def project_agent_core(state: TravelAgentState) -> dict[str, Any] | None:
    store = getattr(state, "agent_core_store", None)
    if not isinstance(store, AgentCoreStore):
        return None
    return store.project().model_dump(mode="json")


def _claim_decisions_payload(latest_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    review = latest_outputs.get("evidence_review") or {}
    payload = review.get("payload") or {}
    return list(payload.get("claim_decisions") or [])


def _gap_payload(latest_outputs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    review = latest_outputs.get("evidence_review") or {}
    payload = review.get("payload") or {}
    return list(payload.get("gaps") or [])


def _evidence_summary_payload(
    latest_outputs: dict[str, dict[str, Any]],
    *,
    count: int,
    source_counts: Counter,
    usage_role_counts: Counter,
    strength_counts: Counter,
) -> dict[str, Any]:
    claim_decisions = _claim_decisions_payload(latest_outputs)
    adopted_ids = {
        evidence_id
        for decision in claim_decisions
        for evidence_id in (decision.get("adopted_evidence_ids") or [])
    }
    rejected_ids = {
        evidence_id
        for decision in claim_decisions
        for evidence_id in (decision.get("rejected_evidence_ids") or [])
    }
    research = latest_outputs.get("research_plan") or {}
    research_payload = research.get("payload") or {}
    acquisition = latest_outputs.get("evidence_acquisition") or {}
    acquisition_payload = acquisition.get("payload") or {}
    completed_search_task_ids = (
        acquisition_payload.get("completed_search_task_ids")
        or research_payload.get("completed_search_task_ids")
        or []
    )
    return {
        "count": count,
        "source_type_counts": dict(source_counts),
        "usage_role_counts": dict(usage_role_counts),
        "strength_counts": dict(strength_counts),
        "adopted_evidence_count": len(adopted_ids),
        "rejected_evidence_count": len(rejected_ids),
        "effective_query_count": (
            len(completed_search_task_ids)
            if isinstance(completed_search_task_ids, list)
            else 0
        ),
    }


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
    """Small append-oriented store for runtime audit, inspection and artifact replay."""

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
            event_id = cursor.lastrowid
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
            row = connection.execute("SELECT * FROM run WHERE run_id = ?", (run_id,)).fetchone()
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
