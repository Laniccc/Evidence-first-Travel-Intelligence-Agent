"""Public runtime entry point for the Deep Research Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent_core.memory_store import MemoryAgentStore
from app.agent_core.sqlite_store import SQLiteAgentStore
from app.agent_core.store import AgentCoreStore
from app.agent_core.supervisor import AgentCoreSupervisor
from app.config import get_settings


class AgentCoreRuntime:
    """Create runs, execute the supervisor, and return results."""

    def __init__(
        self,
        *,
        tools_registry: Any | None = None,
        llm_client: Any = None,
        rag_store: Any = None,
        embedding_fn: Any = None,
    ) -> None:
        self.tools_registry = tools_registry
        self.llm_client = llm_client
        self.rag_store = rag_store
        self.embedding_fn = embedding_fn
        self._stores: dict[str, AgentCoreStore] = {}

    def get_store(self, run_id: str) -> AgentCoreStore | None:
        return self._stores.get(run_id)

    async def run(
        self,
        *,
        query: str,
        user_context: dict | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        store = self._create_store()
        store.create_run(query, session_id=session_id)
        self._stores[store.run_id] = store

        supervisor = AgentCoreSupervisor(
            store,
            tools_registry=self.tools_registry,
            llm_client=self.llm_client,
            rag_store=self.rag_store,
            embedding_fn=self.embedding_fn,
        )
        result = await supervisor.run(query=query, user_context=user_context or {})

        result["session_id"] = session_id
        return result

    def _create_store(self) -> AgentCoreStore:
        settings = get_settings()
        backend = getattr(settings, "agent_core_store_backend", "memory")
        if backend == "sqlite":
            return SQLiteAgentStore(Path(settings.agent_core_store_sqlite_path))
        return MemoryAgentStore()
