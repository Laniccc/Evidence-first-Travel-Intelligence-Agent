"""Agent Core Store — abstract base class.

The Store is the single source of truth for all agent state. Every phase tool
writes records through the Store; no phase tool may mutate state directly.

Two implementations are provided:
- MemoryAgentStore (test-only, in-memory dicts)
- SQLiteAgentStore (default local runtime, persistent)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.agent_core.state.models import (
    ArtifactRecord,
    EvidenceRecord,
    JobRecord,
    PhaseState,
    QualityCheckRecord,
    RunProjection,
    RunState,
    TopicCard,
    TopicState,
)


class AgentCoreStore(ABC):
    """Abstract store for Agent Core state-space records.

    All mutation methods return the created/updated record.
    Read methods return projections or lists.
    """

    run_id: str

    # ── Run ───────────────────────────────────────────────────────────────

    @abstractmethod
    def create_run(self, raw_query: str, *, session_id: str | None = None) -> RunState:
        """Create a new run from a user query."""
        ...

    @abstractmethod
    def get_run(self) -> RunState:
        """Return the current run state."""
        ...

    # ── Topics ────────────────────────────────────────────────────────────

    @abstractmethod
    def create_topic(
        self,
        *,
        task_class: str,
        user_question: str,
        normalized_claim: str,
        phase_order: list[str] | None = None,
    ) -> TopicState:
        """Create a new topic thread within this run."""
        ...

    @abstractmethod
    def get_topic(self, topic_id: str) -> TopicState:
        """Return a topic by ID."""
        ...

    @abstractmethod
    def list_topics(self) -> list[TopicState]:
        """Return all topics for this run."""
        ...

    @abstractmethod
    def update_topic(self, topic_id: str, **fields: Any) -> TopicState:
        """Update mutable fields on a topic (status, current_phase, confidence)."""
        ...

    # ── Phases ────────────────────────────────────────────────────────────

    @abstractmethod
    def set_phase(
        self,
        phase_name: str,
        status: str,
        *,
        topic_id: str | None = None,
        error: str | None = None,
    ) -> PhaseState:
        """Create or update a phase state record."""
        ...

    @abstractmethod
    def get_phase(self, phase_id: str) -> PhaseState:
        """Return a phase by ID."""
        ...

    @abstractmethod
    def list_phases(self, *, topic_id: str | None = None) -> list[PhaseState]:
        """Return all phases, optionally filtered by topic."""
        ...

    # ── Artifacts ─────────────────────────────────────────────────────────

    @abstractmethod
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
        """Append a new artifact version."""
        ...

    @abstractmethod
    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        """Return an artifact by ID."""
        ...

    @abstractmethod
    def list_artifacts(
        self,
        *,
        topic_id: str | None = None,
        phase_name: str | None = None,
        artifact_type: str | None = None,
    ) -> list[ArtifactRecord]:
        """Return artifacts, optionally filtered."""
        ...

    @abstractmethod
    def approve_artifact(self, artifact_id: str) -> ArtifactRecord:
        """Mark an artifact as approved."""
        ...

    @abstractmethod
    def reject_artifact(
        self, artifact_id: str, *, reason: str
    ) -> ArtifactRecord:
        """Mark an artifact as rejected with a reason."""
        ...

    # ── Evidence ──────────────────────────────────────────────────────────

    @abstractmethod
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
        """Append a new evidence record."""
        ...

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> EvidenceRecord:
        """Return an evidence record by ID."""
        ...

    @abstractmethod
    def list_evidence(
        self,
        *,
        topic_id: str | None = None,
        usage_role: str | None = None,
    ) -> list[EvidenceRecord]:
        """Return evidence records, optionally filtered."""
        ...

    @abstractmethod
    def set_evidence_usage(
        self, evidence_id: str, usage_role: str
    ) -> EvidenceRecord:
        """Update the usage_role of an evidence record."""
        ...

    # ── Quality Checks ────────────────────────────────────────────────────

    @abstractmethod
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
        """Append a quality check record."""
        ...

    @abstractmethod
    def get_quality_check(self, check_id: str) -> QualityCheckRecord:
        """Return a quality check by ID."""
        ...

    @abstractmethod
    def list_quality_checks(
        self, *, artifact_id: str | None = None
    ) -> list[QualityCheckRecord]:
        """Return quality checks, optionally filtered by artifact."""
        ...

    # ── Jobs ──────────────────────────────────────────────────────────────

    @abstractmethod
    def append_job(
        self,
        *,
        phase_name: str,
        tool_name: str,
        status: str = "queued",
        topic_id: str | None = None,
        input: dict[str, Any] | None = None,
    ) -> JobRecord:
        """Create a new job record."""
        ...

    @abstractmethod
    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        """Update a job's status or output."""
        ...

    @abstractmethod
    def get_job(self, job_id: str) -> JobRecord:
        """Return a job by ID."""
        ...

    @abstractmethod
    def list_jobs(
        self, *, topic_id: str | None = None, status: str | None = None
    ) -> list[JobRecord]:
        """Return jobs, optionally filtered."""
        ...

    # ── Rollback ──────────────────────────────────────────────────────────

    @abstractmethod
    def rollback_to_phase(
        self, phase_name: str, *, topic_id: str | None = None, reason: str
    ) -> PhaseState:
        """Rollback to a phase, superseding later phases."""
        ...

    # ── Projection ────────────────────────────────────────────────────────

    @abstractmethod
    def project_run(self) -> RunProjection:
        """Build the read-model projection of the current run."""
        ...

    @abstractmethod
    def project_topic(self, topic_id: str) -> TopicCard:
        """Build the read-model projection of a single topic."""
        ...
