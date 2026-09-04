"""Liveness and dependency-aware readiness probes."""

from __future__ import annotations

from app.contracts.response import AgentHealthResponse


class ReadinessProbe:
    def __init__(self, *, sqlite_probe, qdrant_probe, runtime_checks=None) -> None:
        self._sqlite_probe = sqlite_probe
        self._qdrant_probe = qdrant_probe
        self._runtime_checks = runtime_checks

    def checks(self) -> dict[str, str]:
        return {
            "sqlite": _check(self._sqlite_probe),
            "qdrant": _check(self._qdrant_probe),
            **(self._runtime_checks() if self._runtime_checks else {}),
        }


def build_live_response(settings) -> AgentHealthResponse:
    return AgentHealthResponse(
        status="ok",
        service="agent-python",
        version=settings.app_version if settings else "unknown",
        ready=None,
        checks={"process": "ok"},
    )


def build_ready_response(settings, probe: ReadinessProbe | None) -> AgentHealthResponse:
    checks = probe.checks() if probe else {"sqlite": "unavailable", "qdrant": "unavailable"}
    sqlite_ready = checks["sqlite"] == "ok"
    qdrant_ready = checks["qdrant"] == "ok"
    requires_qdrant = bool(settings and settings.readiness_requires_qdrant)
    ready = sqlite_ready and (qdrant_ready or not requires_qdrant)
    degraded = ready and (not qdrant_ready or any(value in {"credentials_missing", "unavailable", "configuration_missing"}
                         for value in checks.values()))
    return AgentHealthResponse(
        status="degraded" if degraded else ("ok" if ready else "not_ready"),
        service="agent-python",
        version=settings.app_version if settings else "unknown",
        ready=ready,
        checks=checks,
    )


def build_health_response(settings) -> AgentHealthResponse:
    """Compatibility health result; new deployments should use live/ready."""
    return build_live_response(settings)


def _check(probe) -> str:
    try:
        return "ok" if probe() else "unavailable"
    except Exception:
        return "unavailable"


__all__ = [
    "ReadinessProbe",
    "build_health_response",
    "build_live_response",
    "build_ready_response",
]
