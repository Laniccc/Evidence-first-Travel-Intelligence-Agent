"""Tool surface for Research Agent phases."""

from __future__ import annotations

from typing import Any

from app.agent_core.phases import (
    run_evidence_acquisition,
    run_evidence_extraction,
    run_knowledge_retrieval,
    run_knowledge_upsert,
    run_planning,
    run_synthesis,
)
from app.agent_core.state.models import PhaseToolResult
from app.agent_core.store import AgentCoreStore


class AgentCoreToolSurface:
    """Concrete phase-tool facade for 6-phase research pipeline."""

    def __init__(
        self,
        store: AgentCoreStore,
        *,
        tools_registry: Any | None = None,
        llm_client: Any = None,
        rag_store: Any = None,
        embedding_fn: Any = None,
    ) -> None:
        self.store = store
        self.tools_registry = tools_registry
        self.llm_client = llm_client
        self.rag_store = rag_store
        self.embedding_fn = embedding_fn

    def ingress(self, *, query: str, user_context: dict | None = None) -> str:
        """Create run record. Returns run_id."""
        session_id = (user_context or {}).get("session_id")
        try:
            return self.store.get_run().run_id
        except Exception:
            pass
        run = self.store.create_run(query, session_id=session_id)
        return run.run_id

    async def planning(self, *, query: str, run_id: str, skills_prompt: str = "") -> PhaseToolResult:
        return await run_planning(self.store, run_id=run_id, query=query, llm_client=self.llm_client, skills_prompt=skills_prompt)

    async def knowledge_retrieval(self, *, query: str, run_id: str) -> PhaseToolResult:
        return await run_knowledge_retrieval(
            self.store, run_id=run_id, topic_id=None, query=query,
            rag_store=self.rag_store, embedding_fn=self.embedding_fn,
        )

    async def evidence_acquisition(self, *, run_id: str, queries: list | None = None, existing_evidence_count: int = 0, direct_urls: list[str] | None = None, retry_round: int = 1) -> PhaseToolResult:
        return await run_evidence_acquisition(
            self.store, run_id=run_id, topic_id=None,
            queries=queries or [], tool_registry=self.tools_registry,
            existing_evidence_count=existing_evidence_count,
            direct_urls=direct_urls or [],
            retry_round=retry_round,
        )

    async def evidence_extraction(self, *, run_id: str, evidence_records: list | None = None) -> PhaseToolResult:
        return await run_evidence_extraction(
            self.store, run_id=run_id, topic_id=None,
            evidence_records=evidence_records or [],
            llm_client=self.llm_client, tool_registry=self.tools_registry,
        )

    async def synthesis(self, *, query: str, run_id: str, evidence_records: list | None = None, skills_prompt: str = "") -> PhaseToolResult:
        return await run_synthesis(
            self.store, run_id=run_id, topic_id=None,
            query=query, evidence_records=evidence_records or [],
            llm_client=self.llm_client,
            skills_prompt=skills_prompt,
        )

    async def knowledge_upsert(self, *, run_id: str, evidence_records: list | None = None) -> PhaseToolResult:
        return await run_knowledge_upsert(
            self.store, run_id=run_id, topic_id=None,
            evidence_records=evidence_records or [],
            rag_store=self.rag_store, embedding_fn=self.embedding_fn,
        )
