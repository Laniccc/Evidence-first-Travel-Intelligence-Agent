"""Projection — the read model for supervisor, UI, debug, and API.

The projection is built from the Store and MUST NOT mutate any records.
It is the only surface the root agent uses to decide next actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agent_core.state.lifecycle import FULL_PHASE_ORDER, TERMINAL_STATUSES
from app.agent_core.state.models import (
    AdoptedFact,
    EvidenceGap,
    PhaseCard,
    RejectedFact,
    RunProjection,
    TopicCard,
)

if TYPE_CHECKING:
    from app.agent_core.memory_store import MemoryAgentStore


def build_run_projection(store: "MemoryAgentStore") -> RunProjection:
    """Build a complete RunProjection from an in-memory store cache.

    This function is pure: it reads the cache dicts and constructs the
    projection without side effects.
    """
    run = store._run
    if run is None:
        return RunProjection(
            run_id=store.run_id,
            status="created",
            raw_query="",
        )

    # ── Topic cards ────────────────────────────────────────────────────
    topic_cards: list[TopicCard] = []
    for topic in store._topics.values():
        topic_cards.append(TopicCard(
            topic_id=topic.topic_id,
            task_class=topic.task_class,
            user_question=topic.user_question,
            status=topic.status,
            current_phase=topic.current_phase,
            confidence=topic.confidence,
        ))

    # ── Phase cards ────────────────────────────────────────────────────
    phase_cards: list[PhaseCard] = []
    for phase in store._phases.values():
        phase_cards.append(PhaseCard(
            phase_id=phase.phase_id,
            phase_name=phase.phase_name,
            topic_id=phase.topic_id,
            status=phase.status,
            attempt=phase.attempt,
            approved_artifact_id=phase.approved_artifact_id,
            error=phase.error,
        ))

    # ── Adopted facts ──────────────────────────────────────────────────
    adopted_facts: list[AdoptedFact] = []
    for a in store._artifacts.values():
        if a.status == "approved" and a.artifact_type == "claim_decision":
            payload = a.payload or {}
            if payload.get("free_policy"):
                policy = payload["free_policy"]
                if isinstance(policy, dict):
                    claim = str(policy.get("text") or "")
                    source_refs = list(policy.get("source_refs") or [])
                else:
                    claim = str(policy)
                    source_refs = []
                adopted_facts.append(AdoptedFact(
                    claim=claim,
                    source_refs=source_refs,
                    confidence=payload.get("confidence", "medium"),
                ))
            for fact in payload.get("adopted_prices", []):
                if isinstance(fact, dict):
                    adopted_facts.append(AdoptedFact(
                        claim=f"{fact.get('product_name', 'ticket')}: {fact.get('price', '?')}",
                        source_refs=fact.get("source_refs", []),
                        confidence=payload.get("confidence", "medium"),
                    ))

    # ── Rejected facts ─────────────────────────────────────────────────
    rejected_facts: list[RejectedFact] = []
    seen_rejected: set[tuple[str, str, str]] = set()
    for ev in store._evidence.values():
        if ev.usage_role == "rejected":
            for claim in ev.claims:
                claim_text = claim.get("text", str(claim)) if isinstance(claim, dict) else str(claim)
                reason = f"Rejected from {ev.source_name}"
                key = (ev.evidence_id, reason, claim_text)
                if key in seen_rejected:
                    continue
                seen_rejected.add(key)
                rejected_facts.append(RejectedFact(
                    claim=claim_text,
                    reason=reason,
                    source_refs=[ev.evidence_id],
                ))

    # Also include rejected artifacts info
    for a in store._artifacts.values():
        if a.status == "rejected" and a.rejection_reasons:
            rejected_facts.append(RejectedFact(
                claim=f"[{a.artifact_type}] {a.phase_name}",
                reason="; ".join(a.rejection_reasons),
                source_refs=[a.artifact_id],
            ))

    # ── Evidence gaps ──────────────────────────────────────────────────
    evidence_gaps: list[EvidenceGap] = []
    first_class_gap_keys: set[tuple[str | None, str]] = set()
    # Detect first-class evidence gap artifacts.
    for artifact in store._artifacts.values():
        if artifact.artifact_type != "evidence_gap":
            continue
        first_class_gap_keys.add((artifact.topic_id, artifact.phase_name))
        payload = artifact.payload or {}
        evidence_gaps.append(EvidenceGap(
            description=str(
                payload.get("missing_evidence_need")
                or payload.get("reason")
                or "evidence gap"
            ),
            priority=str(payload.get("priority") or "high"),
            topic_id=artifact.topic_id,
            phase_name=artifact.phase_name,
            claim_type=payload.get("claim_type"),
            suggested_tools=list(payload.get("suggested_tools") or []),
            status=str(payload.get("status") or "open"),
        ))

    # Detect gaps from failed or revision-needed phases.
    for phase in store._phases.values():
        if (phase.topic_id, phase.phase_name) in first_class_gap_keys:
            continue
        if phase.status == "failed" and phase.error:
            evidence_gaps.append(EvidenceGap(
                description=phase.error,
                priority="high",
                topic_id=phase.topic_id,
                phase_name=phase.phase_name,
            ))
        if phase.status == "needs_revision" and phase.error:
            evidence_gaps.append(EvidenceGap(
                description=phase.error,
                priority="high",
                topic_id=phase.topic_id,
                phase_name=phase.phase_name,
            ))

    # Detect missing evidence: topics with no evidence records
    for topic in store._topics.values():
        has_evidence = any(
            ev.topic_id == topic.topic_id or ev.topic_id is None
            for ev in store._evidence.values()
        )
        topic_phase = _find_phase_in_store(store, "evidence_acquisition", topic.topic_id)
        if not has_evidence and topic_phase and topic_phase.status in {"draft", "running"}:
            evidence_gaps.append(EvidenceGap(
                description=f"Topic '{topic.user_question}' has no evidence yet",
                priority="medium",
                topic_id=topic.topic_id,
            ))

    # ── Visible actions ────────────────────────────────────────────────
    evidence_gaps = _dedupe_gaps(evidence_gaps)

    visible_actions: list[str] = []
    current_phase = _determine_current_phase(store)

    if current_phase:
        visible_actions.append(f"run_{current_phase}")
        # Add relevant control tools
        phase_state = _find_phase_in_store(store, current_phase)
        if phase_state:
            if phase_state.status == "pending_review":
                visible_actions.append("approve_phase")
                visible_actions.append("reject_artifact")
            if phase_state.status == "failed":
                visible_actions.append("retry_phase")
            visible_actions.append("rollback_to_phase")

    # If any jobs are queued or running, reconcile is visible
    if any(j.status in {"queued", "running"} for j in store._jobs.values()):
        visible_actions.append("reconcile_job")

    # ── Blocked reasons ────────────────────────────────────────────────
    blocked_reasons: list[str] = []
    for phase in store._phases.values():
        if phase.status == "blocked":
            blocked_reasons.append(f"{phase.phase_name}: {phase.error or 'no reason given'}")

    # ── Determine run-level status ─────────────────────────────────────
    run_status = run.status
    all_topics_terminal = all(
        t.status in TERMINAL_STATUSES for t in store._topics.values()
    )
    if not store._topics:
        all_topics_terminal = run_status in TERMINAL_STATUSES

    # Limited/blocked topic outcomes take precedence over delivery's mechanical
    # phase success. Delivery can succeed as a phase while the run is still a
    # limited safe failure.
    delivery_phase = _find_phase_in_store(store, "delivery")
    if any(t.status == "succeeded_limited" for t in store._topics.values()):
        run_status = "succeeded_limited"
    elif any(t.status == "blocked_need_evidence" for t in store._topics.values()):
        run_status = "blocked_need_evidence"
    elif delivery_phase and delivery_phase.status == "succeeded":
        run_status = "succeeded"
    elif blocked_reasons and not all_topics_terminal:
        run_status = "blocked"
    elif all_topics_terminal:
        run_status = "succeeded"

    final_answer: str | None = None
    delivery_artifacts = [
        a
        for a in store._artifacts.values()
        if a.phase_name == "delivery" and a.artifact_type == "final_answer"
    ]
    if delivery_artifacts:
        final_answer = str(delivery_artifacts[-1].payload.get("answer") or "") or None

    return RunProjection(
        run_id=store.run_id,
        status=run_status,
        raw_query=run.raw_query,
        current_phase=current_phase,
        topic_cards=topic_cards,
        phase_cards=phase_cards,
        adopted_facts=adopted_facts,
        rejected_facts=rejected_facts,
        evidence_gaps=evidence_gaps,
        visible_actions=visible_actions,
        blocked_reasons=blocked_reasons,
        final_answer=final_answer,
    )


def build_topic_projection(store: "MemoryAgentStore", topic_id: str) -> TopicCard:
    """Build projection for a single topic."""
    topic = store._topics.get(topic_id)
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


def _dedupe_gaps(gaps: list[EvidenceGap]) -> list[EvidenceGap]:
    by_key: dict[tuple[str, str | None, str | None], EvidenceGap] = {}
    order: list[tuple[str, str | None, str | None]] = []
    for gap in gaps:
        key = (gap.description, gap.topic_id, gap.phase_name)
        if key not in by_key:
            order.append(key)
        by_key[key] = gap
    return [by_key[key] for key in order]


def _find_phase_in_store(
    store: "MemoryAgentStore",
    phase_name: str,
    topic_id: str | None = None,
) -> "PhaseState | None":
    from app.agent_core.state.models import PhaseState
    for phase in store._phases.values():
        if phase.phase_name == phase_name and phase.topic_id == topic_id:
            return phase
    return None


def _determine_current_phase(store: "MemoryAgentStore") -> str | None:
    """Determine the current active phase from the store."""
    # First check if run has a current_phase set
    if store._run and store._run.current_phase:
        return store._run.current_phase

    # Find first non-terminal phase in canonical order
    for phase_name in FULL_PHASE_ORDER:
        for phase in store._phases.values():
            if phase.phase_name == phase_name and phase.status not in TERMINAL_STATUSES:
                return phase_name

    # Fall back to last non-terminal run-level phase
    for phase_name in reversed(FULL_PHASE_ORDER):
        for phase in store._phases.values():
            if phase.phase_name == phase_name and phase.topic_id is None:
                return phase_name

    return None
