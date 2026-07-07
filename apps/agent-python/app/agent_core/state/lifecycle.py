"""Phase statuses and transition rules for the Agent Core lifecycle.

Allowed phase statuses:

    not_started  →  running  →  draft  →  pending_review  →  approved  →  succeeded
                     ↓           ↓            ↓                  ↓
                   failed    (retry)    needs_revision      rolled_back
                     ↓                        ↓                  ↓
                   running               running           superseded
"""

from __future__ import annotations

from typing import Literal, get_args

# ── Allowed statuses ────────────────────────────────────────────────────────

PhaseStatus = Literal[
    "not_started",
    "running",
    "draft",
    "pending_review",
    "approved",
    "needs_revision",
    "failed",
    "blocked",
    "rolled_back",
    "skipped",
    "superseded",
    "succeeded",
]

ALL_STATUSES: tuple[str, ...] = get_args(PhaseStatus)

# ── Transition rules ────────────────────────────────────────────────────────

TRANSITION_MAP: dict[str, set[str]] = {
    "not_started":     {"running"},
    "running":         {"draft", "failed", "blocked", "succeeded"},
    "draft":           {"pending_review", "failed", "succeeded", "approved"},
    "pending_review":  {"approved", "needs_revision"},
    "approved":        {"succeeded", "rolled_back"},
    "needs_revision":  {"running"},
    "failed":          {"running", "skipped"},
    "blocked":         {"running", "failed", "skipped"},
    "rolled_back":     {"running"},
    "skipped":         set(),
    "superseded":      set(),
    "succeeded":       set(),
}

# A later phase is superseded when an earlier phase is rolled back.
# For convenience we also allow explicit supersede transitions.
TRANSITION_MAP["draft"] = TRANSITION_MAP["draft"] | {"superseded"}
TRANSITION_MAP["pending_review"] = TRANSITION_MAP["pending_review"] | {"superseded"}
TRANSITION_MAP["approved"] = TRANSITION_MAP["approved"] | {"superseded"}

# ── Phase orders ────────────────────────────────────────────────────────────

# Research Agent pipeline: 6 sequential phases + 1 delivery gate
RUN_PHASE_ORDER: tuple[str, ...] = (
    "planning",
    "knowledge_retrieval",
    "evidence_acquisition",
    "evidence_extraction",
    "synthesis",
    "knowledge_upsert",
)

# In the research agent, all phases are part of the main run — no separate topic-level ordering.
# Topics (sub-questions) are processed within each phase's own loop.
TOPIC_PHASE_ORDER: tuple[str, ...] = ()

# Full canonical order used for phase ordering in projections
FULL_PHASE_ORDER: tuple[str, ...] = RUN_PHASE_ORDER

TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "blocked", "skipped", "superseded"})


# ── Validation ──────────────────────────────────────────────────────────────


def validate_transition(from_status: str, to_status: str) -> bool:
    """Return True if the transition is allowed by the lifecycle rules.

    Also returns True for identity transitions (no-op).
    """
    if from_status == to_status:
        return True
    allowed = TRANSITION_MAP.get(from_status)
    if allowed is None:
        return False
    return to_status in allowed


def validate_transition_strict(from_status: str, to_status: str) -> None:
    """Raise ValueError if the transition is not allowed."""
    if not validate_transition(from_status, to_status):
        raise ValueError(
            f"Invalid phase transition: {from_status} → {to_status}. "
            f"Allowed targets from {from_status}: {TRANSITION_MAP.get(from_status, set())}"
        )


def is_terminal(status: str) -> bool:
    """Return True if the status is terminal (no further transitions expected)."""
    return status in TERMINAL_STATUSES


def phase_index_in_order(phase_name: str) -> int:
    """Return the canonical index of a phase in FULL_PHASE_ORDER, or -1 if unknown."""
    try:
        return FULL_PHASE_ORDER.index(phase_name)
    except ValueError:
        return -1


def phases_after(phase_name: str) -> tuple[str, ...]:
    """Return phases that come after `phase_name` in the canonical order."""
    idx = phase_index_in_order(phase_name)
    if idx < 0:
        return ()
    return FULL_PHASE_ORDER[idx + 1 :]
