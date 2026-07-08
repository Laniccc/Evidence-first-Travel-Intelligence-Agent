"""In-memory Agent Core Store (test-only).

This is a full implementation of AgentCoreStore backed by dicts. It is
suitable for tests and rapid prototyping; production should use SQLiteAgentStore.
"""

from __future__ import annotations

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
from app.agent_core.state.lifecycle import (
    FULL_PHASE_ORDER,
    phases_after,
    validate_transition_strict,
)
from app.agent_core.state.models import (
    AdoptedFact,
    ArtifactRecord,
    EvidenceGap,
    EvidenceRecord,
    JobRecord,
    PhaseCard,
    PhaseState,
    QualityCheckRecord,
    RejectedFact,
    RunProjection,
    RunState,
    TopicCard,
    TopicState,
    utc_now_iso,
)
from app.agent_core.store import AgentCoreStore


class MemoryAgentStore(AgentCoreStore):
    """In-memory implementation of the Agent Core Store."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or generate_run_id()
        self._run: RunState | None = None
        self._topics: dict[str, TopicState] = {}
        self._phases: dict[str, PhaseState] = {}       # phase_id -> PhaseState
        self._artifacts: dict[str, ArtifactRecord] = {}
        self._evidence: dict[str, EvidenceRecord] = {}
        self._quality_checks: dict[str, QualityCheckRecord] = {}
        self._jobs: dict[str, JobRecord] = {}

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _now() -> str:
        return utc_now_iso()

    def _assert_run_exists(self) -> RunState:
        if self._run is None:
            raise ValueError("Run has not been created yet")
        return self._run

    # ── Run ───────────────────────────────────────────────────────────────

    def create_run(self, raw_query: str, *, session_id: str | None = None) -> RunState:
        now = self._now()
        self._run = RunState(
            run_id=self.run_id,
            session_id=session_id,
            raw_query=raw_query,
            status="created",
            created_at=now,
            updated_at=now,
        )
        return self._run

    def get_run(self) -> RunState:
        return self._assert_run_exists()

    # ── Topics ────────────────────────────────────────────────────────────

    def create_topic(
        self,
        *,
        task_class: str,
        user_question: str,
        normalized_claim: str,
        phase_order: list[str] | None = None,
    ) -> TopicState:
        self._assert_run_exists()
        now = self._now()
        topic = TopicState(
            topic_id=generate_topic_id(),
            run_id=self.run_id,
            task_class=task_class,
            user_question=user_question,
            normalized_claim=normalized_claim,
            phase_order=phase_order or [],
            created_at=now,
            updated_at=now,
        )
        self._topics[topic.topic_id] = topic
        # Track active topic
        if topic.topic_id not in self._run.active_topic_ids:
            self._run.active_topic_ids.append(topic.topic_id)
            self._run.updated_at = now
        return topic

    def get_topic(self, topic_id: str) -> TopicState:
        if topic_id not in self._topics:
            raise ValueError(f"Unknown topic: {topic_id}")
        return self._topics[topic_id]

    def list_topics(self) -> list[TopicState]:
        return list(self._topics.values())

    def update_topic(self, topic_id: str, **fields: Any) -> TopicState:
        topic = self.get_topic(topic_id)
        for key, value in fields.items():
            if hasattr(topic, key):
                setattr(topic, key, value)
        topic.updated_at = self._now()
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
        self._assert_run_exists()
        # Find existing phase or create new one
        existing = self._find_phase(phase_name, topic_id=topic_id)
        now = self._now()
        if existing:
            old_status = existing.status
            validate_transition_strict(old_status, status)
            existing.status = status
            if error is not None:
                existing.error = error
            existing.updated_at = now
            if status == "running" and old_status != "running":
                existing.attempt += 1
            return existing
        else:
            phase = PhaseState(
                phase_id=generate_phase_id(),
                run_id=self.run_id,
                topic_id=topic_id,
                phase_name=phase_name,
                status=status,
                error=error,
                created_at=now,
                updated_at=now,
            )
            self._phases[phase.phase_id] = phase
            # Update run-level current_phase if this is a run-level phase
            if topic_id is None:
                self._run.current_phase = phase_name
                self._run.updated_at = now
            else:
                topic = self._topics.get(topic_id)
                if topic:
                    topic.current_phase = phase_name
                    topic.updated_at = now
            return phase

    def _find_phase(self, phase_name: str, *, topic_id: str | None = None) -> PhaseState | None:
        for phase in self._phases.values():
            if phase.phase_name == phase_name and phase.topic_id == topic_id:
                return phase
        return None

    def get_phase(self, phase_id: str) -> PhaseState:
        if phase_id not in self._phases:
            raise ValueError(f"Unknown phase: {phase_id}")
        return self._phases[phase_id]

    def list_phases(self, *, topic_id: str | None = None) -> list[PhaseState]:
        result = []
        for phase in self._phases.values():
            if topic_id is None or phase.topic_id == topic_id:
                result.append(phase)
        return result

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
        self._assert_run_exists()
        # Determine version: count existing artifacts for same phase+type+topic
        existing_count = sum(
            1 for a in self._artifacts.values()
            if a.phase_name == phase_name
            and a.artifact_type == artifact_type
            and a.topic_id == topic_id
        )
        artifact = ArtifactRecord(
            artifact_id=generate_artifact_id(),
            run_id=self.run_id,
            topic_id=topic_id,
            phase_name=phase_name,
            artifact_type=artifact_type,
            version=existing_count + 1,
            status=status,
            payload=payload or {},
            evidence_refs=evidence_refs or [],
            created_by=created_by,
            created_at=self._now(),
        )
        self._artifacts[artifact.artifact_id] = artifact
        # Link artifact to its phase
        phase = self._find_phase(phase_name, topic_id=topic_id)
        if phase and artifact.artifact_id not in phase.output_artifact_refs:
            phase.output_artifact_refs.append(artifact.artifact_id)
            phase.updated_at = self._now()
        return artifact

    def get_artifact(self, artifact_id: str) -> ArtifactRecord:
        if artifact_id not in self._artifacts:
            raise ValueError(f"Unknown artifact: {artifact_id}")
        return self._artifacts[artifact_id]

    def list_artifacts(
        self,
        *,
        topic_id: str | None = None,
        phase_name: str | None = None,
        artifact_type: str | None = None,
    ) -> list[ArtifactRecord]:
        result = []
        for artifact in self._artifacts.values():
            if topic_id is not None and artifact.topic_id != topic_id:
                continue
            if phase_name is not None and artifact.phase_name != phase_name:
                continue
            if artifact_type is not None and artifact.artifact_type != artifact_type:
                continue
            result.append(artifact)
        return sorted(result, key=lambda a: a.created_at)

    def approve_artifact(self, artifact_id: str) -> ArtifactRecord:
        artifact = self.get_artifact(artifact_id)
        if artifact.status not in {"pending_review", "draft"}:
            raise ValueError(
                f"Cannot approve artifact {artifact_id} with status {artifact.status}"
            )
        artifact.status = "approved"
        # Mark the phase as having an approved artifact
        phase = self._find_phase(artifact.phase_name, topic_id=artifact.topic_id)
        if phase:
            phase.approved_artifact_id = artifact_id
            phase.updated_at = self._now()
        return artifact

    def reject_artifact(self, artifact_id: str, *, reason: str) -> ArtifactRecord:
        artifact = self.get_artifact(artifact_id)
        if artifact.status not in {"pending_review", "draft", "approved"}:
            raise ValueError(
                f"Cannot reject artifact {artifact_id} with status {artifact.status}"
            )
        artifact.status = "rejected"
        if reason not in artifact.rejection_reasons:
            artifact.rejection_reasons.append(reason)
        return artifact

    # ── Evidence ──────────────────────────────────────────────────────────

    def append_evidence(
        self,
        *,
        source_name: str,
        source_type: str,
        source_url: str | None = None,
        topic_id: str | None = None,
        source_tier: int = 3,
        claims: list[dict[str, Any]] | None = None,
        raw_payload: dict[str, Any] | None = None,
        reliability: str = "unknown",
    ) -> EvidenceRecord:
        self._assert_run_exists()
        evidence = EvidenceRecord(
            evidence_id=generate_evidence_id(),
            run_id=self.run_id,
            topic_id=topic_id,
            source_name=source_name,
            source_url=source_url,
            source_type=source_type,
            source_tier=source_tier,
            fetched_at=self._now(),
            claims=claims or [],
            raw_payload=raw_payload or {},
            reliability=reliability,
            usage_role="unreviewed",
        )
        self._evidence[evidence.evidence_id] = evidence
        return evidence

    def get_evidence(self, evidence_id: str) -> EvidenceRecord:
        if evidence_id not in self._evidence:
            raise ValueError(f"Unknown evidence: {evidence_id}")
        return self._evidence[evidence_id]

    def list_evidence(
        self,
        *,
        topic_id: str | None = None,
        usage_role: str | None = None,
    ) -> list[EvidenceRecord]:
        result = []
        for ev in self._evidence.values():
            if topic_id is not None and ev.topic_id != topic_id:
                continue
            if usage_role is not None and ev.usage_role != usage_role:
                continue
            result.append(ev)
        return result

    def set_evidence_usage(self, evidence_id: str, usage_role: str) -> EvidenceRecord:
        ev = self.get_evidence(evidence_id)
        ev.usage_role = usage_role
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
        self._assert_run_exists()
        qc = QualityCheckRecord(
            check_id=generate_check_id(),
            run_id=self.run_id,
            topic_id=topic_id,
            phase_name=phase_name,
            artifact_id=artifact_id,
            status=status,
            score=score,
            blocking_issues=blocking_issues or [],
            risks=risks or [],
            revision_instructions=revision_instructions or [],
            created_at=self._now(),
        )
        self._quality_checks[qc.check_id] = qc
        # Link quality check to phase
        phase = self._find_phase(phase_name, topic_id=topic_id)
        if phase:
            phase.quality_check_ref = qc.check_id
            phase.updated_at = self._now()
        return qc

    def get_quality_check(self, check_id: str) -> QualityCheckRecord:
        if check_id not in self._quality_checks:
            raise ValueError(f"Unknown quality check: {check_id}")
        return self._quality_checks[check_id]

    def list_quality_checks(
        self, *, artifact_id: str | None = None
    ) -> list[QualityCheckRecord]:
        result = []
        for qc in self._quality_checks.values():
            if artifact_id is not None and qc.artifact_id != artifact_id:
                continue
            result.append(qc)
        return result

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
        self._assert_run_exists()
        now = self._now()
        job = JobRecord(
            job_id=generate_job_id(),
            run_id=self.run_id,
            topic_id=topic_id,
            phase_name=phase_name,
            tool_name=tool_name,
            status=status,
            input=input or {},
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.job_id] = job
        return job

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        job = self.get_job(job_id)
        if status is not None:
            job.status = status
        if output_ref is not None:
            job.output_ref = output_ref
        if error is not None:
            job.error = error
        job.updated_at = self._now()
        return job

    def get_job(self, job_id: str) -> JobRecord:
        if job_id not in self._jobs:
            raise ValueError(f"Unknown job: {job_id}")
        return self._jobs[job_id]

    def list_jobs(
        self, *, topic_id: str | None = None, status: str | None = None
    ) -> list[JobRecord]:
        result = []
        for job in self._jobs.values():
            if topic_id is not None and job.topic_id != topic_id:
                continue
            if status is not None and job.status != status:
                continue
            result.append(job)
        return result

    # ── Rollback ──────────────────────────────────────────────────────────

    def rollback_to_phase(
        self, phase_name: str, *, topic_id: str | None = None, reason: str
    ) -> PhaseState:
        self._assert_run_exists()
        later_phases = phases_after(phase_name)
        now = self._now()
        for later_name in later_phases:
            later = self._find_phase(later_name, topic_id=topic_id)
            if later:
                later.status = "rolled_back"
                later.error = f"Rolled back to {phase_name}: {reason}"
                later.updated_at = now
        target = self._find_phase(phase_name, topic_id=topic_id)
        if target:
            target.status = "running"
            target.attempt += 1
            target.error = reason
            target.updated_at = now
        else:
            target = self.set_phase(phase_name, "running", topic_id=topic_id, error=reason)
        return target

    # ── Projection ────────────────────────────────────────────────────────

    def project_run(self) -> RunProjection:
        from app.agent_core.projection import build_run_projection

        return build_run_projection(self)

    def project_topic(self, topic_id: str) -> TopicCard:
        topic = self._topics.get(topic_id)
        if topic is None:
            raise ValueError(f"Unknown topic: {topic_id}")
        return TopicCard(
            topic_id=topic.topic_id,
            task_class=topic.task_class,
            user_question=topic.user_question,
            status=topic.status,
            current_phase=topic.current_phase,
            confidence=topic.confidence,
        )
