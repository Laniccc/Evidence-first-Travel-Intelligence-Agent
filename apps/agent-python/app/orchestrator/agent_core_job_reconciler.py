"""Background-style reconciliation helpers for Agent Core jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.orchestrator.agent_core_control_tools import AgentCoreControlTools
from app.orchestrator.agent_core_store import ensure_agent_core_store
from app.schemas.agent_core import ControlToolResult, JobRecord
from app.schemas.user_query import TravelAgentState

JobStatusResolver = Callable[[JobRecord], dict[str, Any] | None]


class AgentCoreJobResolverRegistry:
    def __init__(self) -> None:
        self._resolvers: dict[str, JobStatusResolver] = {}

    def register(self, tool_name: str, resolver: JobStatusResolver) -> None:
        self._resolvers[tool_name] = resolver

    def resolve(self, job: JobRecord) -> dict[str, Any] | None:
        resolver = self._resolvers.get(job.tool_name)
        if resolver is None:
            return None
        return resolver(job)


class AgentCoreJobReconciler:
    """Poll pending jobs and write status updates through control tools."""

    def __init__(
        self,
        resolver: JobStatusResolver | None = None,
        registry: AgentCoreJobResolverRegistry | None = None,
    ) -> None:
        self.resolver = resolver
        self.registry = registry or AgentCoreJobResolverRegistry()
        self.controls = AgentCoreControlTools()

    def reconcile_pending(self, state: TravelAgentState) -> list[ControlToolResult]:
        store = ensure_agent_core_store(state)
        results: list[ControlToolResult] = []
        for job in store.pending_jobs():
            update = self._resolve(job)
            if not update:
                continue
            results.append(
                self.controls.reconcile_job(
                    state,
                    job_id=job.id,
                    status=update.get("status"),
                    output_ref=update.get("output_ref"),
                    error=update.get("error"),
                )
            )
        return results

    def _resolve(self, job: JobRecord) -> dict[str, Any] | None:
        if self.resolver is not None:
            update = self.resolver(job)
            if update:
                return update
        return self.registry.resolve(job)
