"""Control tools for Agent Core state transitions.

Control tools are the ONLY surface allowed to intentionally change phase,
artifact, evidence, or job status. Phase tools return records; control tools
apply transitions after validation.

This replaces the experimental orchestrator/agent_core_control_tools.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent_core.state.lifecycle import validate_transition_strict
from app.agent_core.state.models import (
    PhaseState,
    ArtifactRecord,
    JobRecord,
)
from app.agent_core.store import AgentCoreStore


@dataclass
class ControlToolResult:
    """Result of a control tool invocation."""
    tool_name: str
    status: str  # "succeeded" or "failed"
    message: str = ""
    phase_name: str | None = None
    artifact_id: str | None = None
    job_id: str | None = None
    topic_id: str | None = None
    details: dict[str, Any] | None = None


def approve_phase(
    store: AgentCoreStore,
    *,
    phase_name: str,
    artifact_id: str | None = None,
    topic_id: str | None = None,
    approved_by: str = "root_agent",
) -> ControlToolResult:
    """Approve a phase's output artifact and advance the phase to approved/succeeded.

    If an artifact_id is provided, that specific artifact is approved.
    Otherwise the latest artifact for this phase is approved.
    """
    try:
        # Find the phase
        phases = [p for p in store.list_phases(topic_id=topic_id)
                  if p.phase_name == phase_name]
        if not phases:
            return ControlToolResult(
                tool_name="approve_phase",
                status="failed",
                message=f"No phase found: {phase_name} (topic={topic_id})",
                phase_name=phase_name,
                topic_id=topic_id,
            )

        phase = phases[-1]  # latest attempt

        # Validate transition from current status
        current_status = phase.status
        if current_status not in {"pending_review", "draft"}:
            return ControlToolResult(
                tool_name="approve_phase",
                status="failed",
                message=f"Cannot approve phase {phase_name} with status {current_status}",
                phase_name=phase_name,
                topic_id=topic_id,
            )

        # Approve artifact if specified
        target_artifact_id = artifact_id
        if target_artifact_id:
            try:
                store.approve_artifact(target_artifact_id)
            except ValueError as e:
                return ControlToolResult(
                    tool_name="approve_phase",
                    status="failed",
                    message=str(e),
                    phase_name=phase_name,
                    artifact_id=target_artifact_id,
                    topic_id=topic_id,
                )
        elif phase.output_artifact_refs:
            # Auto-approve the last output artifact
            target_artifact_id = phase.output_artifact_refs[-1]
            try:
                store.approve_artifact(target_artifact_id)
            except ValueError:
                pass

        # Transition phase to approved
        store.set_phase(phase_name, "approved", topic_id=topic_id)

        # Auto-succeed if this is a non-review phase
        if phase_name not in {"evidence_review", "claim_decision", "citation_guard"}:
            pass  # Keep at approved; delivery transitions to succeeded

        return ControlToolResult(
            tool_name="approve_phase",
            status="succeeded",
            message=f"Approved phase {phase_name} by {approved_by}",
            phase_name=phase_name,
            artifact_id=target_artifact_id,
            topic_id=topic_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="approve_phase",
            status="failed",
            message=str(exc),
            phase_name=phase_name,
            topic_id=topic_id,
        )


def reject_artifact(
    store: AgentCoreStore,
    *,
    artifact_id: str,
    reason: str,
) -> ControlToolResult:
    """Reject an artifact with a machine-readable reason.

    The phase is set to needs_revision if the artifact was pending_review.
    """
    try:
        artifact = store.get_artifact(artifact_id)
        store.reject_artifact(artifact_id, reason=reason)

        # Transition phase to needs_revision
        try:
            store.set_phase(artifact.phase_name, "needs_revision",
                          topic_id=artifact.topic_id,
                          error=reason)
        except ValueError:
            pass  # phase may already be in a non-transitionable state

        return ControlToolResult(
            tool_name="reject_artifact",
            status="succeeded",
            message=f"Rejected artifact {artifact_id}: {reason}",
            artifact_id=artifact_id,
            phase_name=artifact.phase_name,
            topic_id=artifact.topic_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="reject_artifact",
            status="failed",
            message=str(exc),
            artifact_id=artifact_id,
        )


def rollback_to_phase(
    store: AgentCoreStore,
    *,
    phase_name: str,
    topic_id: str | None = None,
    reason: str,
) -> ControlToolResult:
    """Rollback to a specific phase, marking later phases as rolled_back.

    This is the primary retry mechanism: rollback to a phase and re-run from there
    without re-executing the entire run.
    """
    try:
        phase = store.rollback_to_phase(phase_name, topic_id=topic_id, reason=reason)
        return ControlToolResult(
            tool_name="rollback_to_phase",
            status="succeeded",
            message=f"Rolled back to {phase_name}: {reason}",
            phase_name=phase_name,
            topic_id=topic_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="rollback_to_phase",
            status="failed",
            message=str(exc),
            phase_name=phase_name,
            topic_id=topic_id,
        )


def retry_phase(
    store: AgentCoreStore,
    *,
    phase_name: str,
    topic_id: str | None = None,
    reason: str,
) -> ControlToolResult:
    """Retry a failed or needs_revision phase.

    This transitions the phase back to running so it can be re-executed.
    Unlike rollback, this does not affect later phases.
    """
    try:
        phases = [p for p in store.list_phases(topic_id=topic_id)
                  if p.phase_name == phase_name]
        if not phases:
            return ControlToolResult(
                tool_name="retry_phase",
                status="failed",
                message=f"No phase found: {phase_name}",
                phase_name=phase_name,
                topic_id=topic_id,
            )

        phase = phases[-1]
        if phase.status not in {"failed", "needs_revision"}:
            return ControlToolResult(
                tool_name="retry_phase",
                status="failed",
                message=f"Cannot retry phase {phase_name} with status {phase.status}",
                phase_name=phase_name,
                topic_id=topic_id,
            )

        store.set_phase(phase_name, "running", topic_id=topic_id, error=reason)

        return ControlToolResult(
            tool_name="retry_phase",
            status="succeeded",
            message=f"Retrying phase {phase_name}: {reason}",
            phase_name=phase_name,
            topic_id=topic_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="retry_phase",
            status="failed",
            message=str(exc),
            phase_name=phase_name,
            topic_id=topic_id,
        )


def skip_phase(
    store: AgentCoreStore,
    *,
    phase_name: str,
    topic_id: str | None = None,
    reason: str,
) -> ControlToolResult:
    """Skip a phase that is not needed (e.g., no evidence to review)."""
    try:
        store.set_phase(phase_name, "skipped", topic_id=topic_id, error=reason)
        return ControlToolResult(
            tool_name="skip_phase",
            status="succeeded",
            message=f"Skipped phase {phase_name}: {reason}",
            phase_name=phase_name,
            topic_id=topic_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="skip_phase",
            status="failed",
            message=str(exc),
            phase_name=phase_name,
            topic_id=topic_id,
        )


def mark_phase_failed(
    store: AgentCoreStore,
    *,
    phase_name: str,
    topic_id: str | None = None,
    error: str,
) -> ControlToolResult:
    """Mark a phase as failed with an error message."""
    try:
        store.set_phase(phase_name, "failed", topic_id=topic_id, error=error)
        return ControlToolResult(
            tool_name="mark_phase_failed",
            status="succeeded",
            message=f"Marked phase {phase_name} as failed: {error}",
            phase_name=phase_name,
            topic_id=topic_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="mark_phase_failed",
            status="failed",
            message=str(exc),
            phase_name=phase_name,
            topic_id=topic_id,
        )


def reconcile_job(
    store: AgentCoreStore,
    *,
    job_id: str,
    status: str | None = None,
    output_ref: str | None = None,
    error: str | None = None,
) -> ControlToolResult:
    """Update a job's status, typically after an external tool call completes."""
    try:
        job = store.update_job(job_id, status=status, output_ref=output_ref, error=error)
        return ControlToolResult(
            tool_name="reconcile_job",
            status="succeeded",
            message=f"Job {job_id} is now {job.status}",
            job_id=job_id,
        )
    except Exception as exc:
        return ControlToolResult(
            tool_name="reconcile_job",
            status="failed",
            message=str(exc),
            job_id=job_id,
        )
