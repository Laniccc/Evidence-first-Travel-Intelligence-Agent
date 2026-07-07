"""ID generation helpers for Agent Core entities.

All IDs use a short prefix for human-readable identification in logs and
debug output, followed by a UUID4 for uniqueness.
"""

from uuid import uuid4


def generate_run_id() -> str:
    return f"run_{uuid4().hex[:12]}"


def generate_topic_id() -> str:
    return f"topic_{uuid4().hex[:12]}"


def generate_phase_id() -> str:
    return f"phase_{uuid4().hex[:12]}"


def generate_artifact_id() -> str:
    return f"art_{uuid4().hex[:12]}"


def generate_evidence_id() -> str:
    return f"ev_{uuid4().hex[:12]}"


def generate_check_id() -> str:
    return f"qc_{uuid4().hex[:12]}"


def generate_job_id() -> str:
    return f"job_{uuid4().hex[:12]}"
