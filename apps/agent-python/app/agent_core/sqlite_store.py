"""SQLite-backed Agent Core Store.

Default local runtime store. Tables mirror the record types:
agent_runs, agent_topics, agent_phases, agent_artifacts, agent_evidence,
agent_quality_checks, agent_jobs, agent_events.

Every write also appends to agent_events for audit/replay.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.agent_core.state.ids import (
    generate_artifact_id,
    generate_check_id,
    generate_evidence_id,
    generate_job_id,
    generate_phase_id,
    generate_run_id,
    generate_topic_id,
)
from app.agent_core.state.lifecycle import phases_after, validate_transition_strict
from app.agent_core.state.models import (
    ArtifactRecord,
    EvidenceRecord,
    JobRecord,
    PhaseState,
    QualityCheckRecord,
    RunProjection,
    RunState,
    TopicState,
    utc_now_iso,
)
from app.agent_core.store import AgentCoreStore
from app.agent_core.memory_store import MemoryAgentStore
from app.agent_core.projection import build_run_projection


class SQLiteAgentStore(AgentCoreStore):
    """SQLite-backed Agent Core Store.

    Maintains an in-memory projection cache (via MemoryAgentStore) for fast
    reads, while persisting every write to SQLite tables.
    """

    def __init__(self, db_path: str | Path, run_id: str | None = None) -> None:
        self.db_path = Path(db_path)
        self.run_id = run_id or generate_run_id()
        self._cache = MemoryAgentStore(run_id=self.run_id)
        self._ensure_schema()

    # ── SQLite helpers ────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    raw_query TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    active_topic_ids TEXT NOT NULL DEFAULT '[]',
                    current_phase TEXT,
                    final_artifact_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_topics (
                    topic_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    user_question TEXT NOT NULL,
                    normalized_claim TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    phase_order TEXT NOT NULL DEFAULT '[]',
                    current_phase TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_phases (
                    phase_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    topic_id TEXT,
                    phase_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'not_started',
                    attempt INTEGER NOT NULL DEFAULT 1,
                    input_artifact_refs TEXT NOT NULL DEFAULT '[]',
                    output_artifact_refs TEXT NOT NULL DEFAULT '[]',
                    quality_check_ref TEXT,
                    approved_artifact_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    topic_id TEXT,
                    phase_name TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'draft',
                    payload TEXT NOT NULL DEFAULT '{}',
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    supersedes TEXT,
                    rejection_reasons TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL DEFAULT 'system',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    topic_id TEXT,
                    source_name TEXT NOT NULL,
                    source_url TEXT,
                    source_type TEXT NOT NULL,
                    fetched_at TEXT,
                    claims TEXT NOT NULL DEFAULT '[]',
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    reliability TEXT NOT NULL DEFAULT 'unknown',
                    usage_role TEXT NOT NULL DEFAULT 'unreviewed',
                    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_quality_checks (
                    check_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    topic_id TEXT,
                    phase_name TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pass',
                    score REAL NOT NULL DEFAULT 0.0,
                    blocking_issues TEXT NOT NULL DEFAULT '[]',
                    risks TEXT NOT NULL DEFAULT '[]',
                    revision_instructions TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    topic_id TEXT,
                    phase_name TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    input TEXT NOT NULL DEFAULT '{}',
                    output_ref TEXT,
                    error TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    retry_policy TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_run
                    ON agent_events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_topics_run
                    ON agent_topics(run_id);
                CREATE INDEX IF NOT EXISTS idx_phases_run_phase
                    ON agent_phases(run_id, phase_name, topic_id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_run_phase
                    ON agent_artifacts(run_id, phase_name, topic_id);
                CREATE INDEX IF NOT EXISTS idx_evidence_run
                    ON agent_evidence(run_id, topic_id);
                CREATE INDEX IF NOT EXISTS idx_jobs_run
                    ON agent_jobs(run_id, topic_id);
            """)

    def _append_event(self, event_type: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_events(run_id, event_type, entity_type, entity_id, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (self.run_id, event_type, entity_type, entity_id,
                 json.dumps(payload, ensure_ascii=False, default=str),
                 utc_now_iso()),
            )

    @staticmethod
    def _serialize_list(value: list[str]) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _deserialize_list(value: str) -> list[str]:
        if not value:
            return []
        return json.loads(value)

    @staticmethod
    def _serialize_dict(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _deserialize_dict(value: str) -> dict[str, Any]:
        if not value:
            return {}
        return json.loads(value)

    # ── Run ───────────────────────────────────────────────────────────────

    def create_run(self, raw_query: str, *, session_id: str | None = None) -> RunState:
        run = self._cache.create_run(raw_query, session_id=session_id)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_runs(run_id, session_id, raw_query, status,
                   active_topic_ids, current_phase, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run.run_id, run.session_id, run.raw_query, run.status,
                 self._serialize_list(run.active_topic_ids), run.current_phase,
                 run.created_at, run.updated_at),
            )
        self._append_event("create_run", "run", run.run_id, run.model_dump(mode="json"))
        return run

    def get_run(self) -> RunState:
        return self._cache.get_run()

    # ── Topics ────────────────────────────────────────────────────────────

    def create_topic(
        self,
        *,
        task_class: str,
        user_question: str,
        normalized_claim: str,
        phase_order: list[str] | None = None,
    ) -> TopicState:
        topic = self._cache.create_topic(
            task_class=task_class,
            user_question=user_question,
            normalized_claim=normalized_claim,
            phase_order=phase_order,
        )
        # Update run
        run = self._cache.get_run()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_topics(topic_id, run_id, task_class, user_question,
                   normalized_claim, status, phase_order, current_phase, confidence,
                   created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (topic.topic_id, topic.run_id, topic.task_class, topic.user_question,
                 topic.normalized_claim, topic.status, self._serialize_list(topic.phase_order),
                 topic.current_phase, topic.confidence, topic.created_at, topic.updated_at),
            )
            conn.execute(
                "UPDATE agent_runs SET active_topic_ids=?, updated_at=? WHERE run_id=?",
                (self._serialize_list(run.active_topic_ids), utc_now_iso(), self.run_id),
            )
        self._append_event("create_topic", "topic", topic.topic_id, topic.model_dump(mode="json"))
        return topic

    def get_topic(self, topic_id: str) -> TopicState:
        return self._cache.get_topic(topic_id)

    def list_topics(self) -> list[TopicState]:
        return self._cache.list_topics()

    def update_topic(self, topic_id: str, **fields: Any) -> TopicState:
        topic = self._cache.update_topic(topic_id, **fields)
        with self._connect() as conn:
            conn.execute(
                """UPDATE agent_topics SET status=?, current_phase=?, confidence=?,
                   updated_at=? WHERE topic_id=?""",
                (topic.status, topic.current_phase, topic.confidence,
                 topic.updated_at, topic.topic_id),
            )
        self._append_event("update_topic", "topic", topic_id, {"fields": fields})
        return topic

    # ── Phases ────────────────────────────────────────────────────────────

    def set_phase(
        self,
        phase_name: str,
        status: str,
        *,
        topic_id: str | None = None,
        error: str | None = None,
    ) -> PhaseState:
        phase = self._cache.set_phase(phase_name, status, topic_id=topic_id, error=error)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT phase_id FROM agent_phases WHERE run_id=? AND phase_name=? AND topic_id IS ?",
                (self.run_id, phase_name, topic_id),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE agent_phases SET status=?, attempt=?, error=?,
                       output_artifact_refs=?, approved_artifact_id=?,
                       quality_check_ref=?, updated_at=?
                       WHERE phase_id=?""",
                    (phase.status, phase.attempt, phase.error,
                     self._serialize_list(phase.output_artifact_refs),
                     phase.approved_artifact_id, phase.quality_check_ref,
                     phase.updated_at, existing["phase_id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO agent_phases(phase_id, run_id, topic_id, phase_name,
                       status, attempt, input_artifact_refs, output_artifact_refs,
                       quality_check_ref, approved_artifact_id, error, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (phase.phase_id, phase.run_id, phase.topic_id, phase.phase_name,
                     phase.status, phase.attempt, self._serialize_list(phase.input_artifact_refs),
                     self._serialize_list(phase.output_artifact_refs), phase.quality_check_ref,
                     phase.approved_artifact_id, phase.error, phase.created_at, phase.updated_at),
                )
        self._append_event("set_phase", "phase", phase.phase_id, phase.model_dump(mode="json"))
        return phase

    def get_phase(self, phase_id: str) -> PhaseState:
        return self._cache.get_phase(phase_id)

    def list_phases(self, *, topic_id: str | None = None) -> list[PhaseState]:
        return self._cache.list_phases(topic_id=topic_id)

    # ── Artifacts ─────────────────────────────────────────────────────────

    def append_artifact(
        self,
        *,
        phase_name: str,
        artifact_type: str,
        status: str,
        payload: dict[str, Any] | None = None,
        topic_id: str | None = None,
        evidence_refs: list[str] | None = None,
        created_by: str = "system",
    ) -> ArtifactRecord:
        artifact = self._cache.append_artifact(
            phase_name=phase_name,
            artifact_type=artifact_type,
            status=status,
            payload=payload,
            topic_id=topic_id,
            evidence_refs=evidence_refs,
            created_by=created_by,
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_artifacts(artifact_id, run_id, topic_id, phase_name,
                   artifact_type, version, status, payload, evidence_refs, supersedes,
                   rejection_reasons, created_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (artifact.artifact_id, artifact.run_id, artifact.topic_id,
                 artifact.phase_name, artifact.artifact_type, artifact.version,
                 artifact.status, self._serialize_dict(artifact.payload),
                 self._serialize_list(artifact.evidence_refs), artifact.supersedes,
                 self._serialize_list(artifact.rejection_reasons),
                 artifact.created_by, artifact.created_at),
            )
        self._append_event("append_artifact", "artifact", artifact.artifact_id,
                          artifact.model_dump(mode="json"))
        return artifact

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        return self._cache.get_artifact(artifact_id)

    def list_artifacts(
        self,
        *,
        topic_id: str | None = None,
        phase_name: str | None = None,
        artifact_type: str | None = None,
    ) -> list[ArtifactRecord]:
        return self._cache.list_artifacts(
            topic_id=topic_id, phase_name=phase_name, artifact_type=artifact_type,
        )

    def approve_artifact(self, artifact_id: str) -> ArtifactRecord:
        artifact = self._cache.approve_artifact(artifact_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE agent_artifacts SET status=? WHERE artifact_id=?",
                (artifact.status, artifact_id),
            )
        self._append_event("approve_artifact", "artifact", artifact_id,
                          {"status": artifact.status})
        return artifact

    def reject_artifact(self, artifact_id: str, *, reason: str) -> ArtifactRecord:
        artifact = self._cache.reject_artifact(artifact_id, reason=reason)
        with self._connect() as conn:
            conn.execute(
                """UPDATE agent_artifacts SET status=?,
                   rejection_reasons=? WHERE artifact_id=?""",
                (artifact.status, self._serialize_list(artifact.rejection_reasons),
                 artifact_id),
            )
        self._append_event("reject_artifact", "artifact", artifact_id,
                          {"reason": reason})
        return artifact

    # ── Evidence ──────────────────────────────────────────────────────────

    def append_evidence(
        self,
        *,
        source_name: str,
        source_type: str,
        source_url: str | None = None,
        topic_id: str | None = None,
        claims: list[dict[str, Any]] | None = None,
        raw_payload: dict[str, Any] | None = None,
        reliability: str = "unknown",
    ) -> EvidenceRecord:
        evidence = self._cache.append_evidence(
            source_name=source_name,
            source_type=source_type,
            source_url=source_url,
            topic_id=topic_id,
            claims=claims,
            raw_payload=raw_payload,
            reliability=reliability,
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_evidence(evidence_id, run_id, topic_id,
                   source_name, source_url, source_type, fetched_at, claims,
                   raw_payload, reliability, usage_role)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (evidence.evidence_id, evidence.run_id, evidence.topic_id,
                 evidence.source_name, evidence.source_url, evidence.source_type,
                 evidence.fetched_at, self._serialize_dict(evidence.claims),
                 self._serialize_dict(evidence.raw_payload), evidence.reliability,
                 evidence.usage_role),
            )
        self._append_event("append_evidence", "evidence", evidence.evidence_id,
                          evidence.model_dump(mode="json"))
        return evidence

    def get_evidence(self, evidence_id: str) -> EvidenceRecord:
        return self._cache.get_evidence(evidence_id)

    def list_evidence(
        self, *, topic_id: str | None = None, usage_role: str | None = None
    ) -> list[EvidenceRecord]:
        return self._cache.list_evidence(topic_id=topic_id, usage_role=usage_role)

    def set_evidence_usage(self, evidence_id: str, usage_role: str) -> EvidenceRecord:
        ev = self._cache.set_evidence_usage(evidence_id, usage_role)
        with self._connect() as conn:
            conn.execute(
                "UPDATE agent_evidence SET usage_role=? WHERE evidence_id=?",
                (usage_role, evidence_id),
            )
        self._append_event("set_evidence_usage", "evidence", evidence_id,
                          {"usage_role": usage_role})
        return ev

    # ── Quality Checks ────────────────────────────────────────────────────

    def append_quality_check(
        self,
        *,
        phase_name: str,
        artifact_id: str,
        status: str,
        score: float,
        topic_id: str | None = None,
        blocking_issues: list[str] | None = None,
        risks: list[str] | None = None,
        revision_instructions: list[str] | None = None,
    ) -> QualityCheckRecord:
        qc = self._cache.append_quality_check(
            phase_name=phase_name,
            artifact_id=artifact_id,
            status=status,
            score=score,
            topic_id=topic_id,
            blocking_issues=blocking_issues,
            risks=risks,
            revision_instructions=revision_instructions,
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_quality_checks(check_id, run_id, topic_id,
                   phase_name, artifact_id, status, score, blocking_issues,
                   risks, revision_instructions, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (qc.check_id, qc.run_id, qc.topic_id, qc.phase_name,
                 qc.artifact_id, qc.status, qc.score,
                 self._serialize_list(qc.blocking_issues),
                 self._serialize_list(qc.risks),
                 self._serialize_list(qc.revision_instructions),
                 qc.created_at),
            )
        self._append_event("append_quality_check", "quality_check", qc.check_id,
                          qc.model_dump(mode="json"))
        return qc

    def get_quality_check(self, check_id: str) -> QualityCheckRecord:
        return self._cache.get_quality_check(check_id)

    def list_quality_checks(self, *, artifact_id: str | None = None) -> list[QualityCheckRecord]:
        return self._cache.list_quality_checks(artifact_id=artifact_id)

    # ── Jobs ──────────────────────────────────────────────────────────────

    def append_job(
        self,
        *,
        phase_name: str,
        tool_name: str,
        status: str = "queued",
        topic_id: str | None = None,
        input: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = self._cache.append_job(
            phase_name=phase_name,
            tool_name=tool_name,
            status=status,
            topic_id=topic_id,
            input=input,
        )
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_jobs(job_id, run_id, topic_id, phase_name,
                   tool_name, status, input, output_ref, error, retry_count,
                   retry_policy, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job.job_id, job.run_id, job.topic_id, job.phase_name,
                 job.tool_name, job.status, self._serialize_dict(job.input),
                 job.output_ref, job.error, job.retry_count,
                 self._serialize_dict(job.retry_policy),
                 job.created_at, job.updated_at),
            )
        self._append_event("append_job", "job", job.job_id, job.model_dump(mode="json"))
        return job

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        job = self._cache.update_job(
            job_id, status=status, output_ref=output_ref, error=error,
        )
        with self._connect() as conn:
            conn.execute(
                """UPDATE agent_jobs SET status=?, output_ref=?, error=?,
                   retry_count=?, updated_at=? WHERE job_id=?""",
                (job.status, job.output_ref, job.error, job.retry_count,
                 job.updated_at, job_id),
            )
        self._append_event("update_job", "job", job_id,
                          {"status": status, "output_ref": output_ref, "error": error})
        return job

    def get_job(self, job_id: str) -> JobRecord:
        return self._cache.get_job(job_id)

    def list_jobs(self, *, topic_id: str | None = None, status: str | None = None) -> list[JobRecord]:
        return self._cache.list_jobs(topic_id=topic_id, status=status)

    # ── Rollback ──────────────────────────────────────────────────────────

    def rollback_to_phase(
        self, phase_name: str, *, topic_id: str | None = None, reason: str
    ) -> PhaseState:
        phase = self._cache.rollback_to_phase(phase_name, topic_id=topic_id, reason=reason)
        with self._connect() as conn:
            # Update rolled-back later phases
            for later_name in phases_after(phase_name):
                conn.execute(
                    """UPDATE agent_phases SET status='rolled_back',
                       error=?, updated_at=?
                       WHERE run_id=? AND phase_name=? AND topic_id IS ?""",
                    (f"Rolled back to {phase_name}: {reason}", utc_now_iso(),
                     self.run_id, later_name, topic_id),
                )
            # Update target phase
            conn.execute(
                """UPDATE agent_phases SET status=?, attempt=?, error=?, updated_at=?
                   WHERE run_id=? AND phase_name=? AND topic_id IS ?""",
                (phase.status, phase.attempt, phase.error, phase.updated_at,
                 self.run_id, phase_name, topic_id),
            )
        self._append_event("rollback", "phase", phase.phase_id,
                          {"phase_name": phase_name, "topic_id": topic_id, "reason": reason})
        return phase

    # ── Projection ────────────────────────────────────────────────────────

    def project_run(self) -> RunProjection:
        return build_run_projection(self._cache)

    def project_topic(self, topic_id: str) -> Any:
        return self._cache.project_topic(topic_id)
