"""Cross-suite evidence safety metrics and release gates."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GateCheck(BaseModel):
    metric: str
    actual: float
    operator: str
    threshold: float
    passed: bool


class ReleaseGateReport(BaseModel):
    passed: bool
    checks: list[GateCheck] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


def grade_release_gates(metrics: dict[str, float]) -> ReleaseGateReport:
    requirements = {
        "recall_at_3": (">=", 0.90),
        "mrr": (">=", 0.85),
        "ndcg_at_5": (">=", 0.90),
        "metadata_filter_accuracy": ("==", 1.0),
        "non_active_leakage_rate": ("==", 0.0),
        "state_path_accuracy": (">=", 0.95),
        "illegal_transitions": ("==", 0.0),
        "stale_vector_rejection": ("==", 1.0),
        "index_rebuild_consistency": ("==", 1.0),
        "unsupported_hard_facts": ("==", 0.0),
        "citation_precision": (">=", 0.95),
        "abstention_precision": (">=", 0.90),
        "replay_consistency": ("==", 1.0),
    }
    checks = []
    for metric, (operator, threshold) in requirements.items():
        actual = float(metrics[metric])
        passed = actual >= threshold if operator == ">=" else actual == threshold
        checks.append(
            GateCheck(
                metric=metric,
                actual=actual,
                operator=operator,
                threshold=threshold,
                passed=passed,
            )
        )
    failures = [
        f"{item.metric}: {item.actual} {item.operator} {item.threshold}"
        for item in checks
        if not item.passed
    ]
    return ReleaseGateReport(passed=not failures, checks=checks, failures=failures)


__all__ = ["GateCheck", "ReleaseGateReport", "grade_release_gates"]
