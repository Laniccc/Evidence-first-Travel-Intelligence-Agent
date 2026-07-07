"""Phase 2: Knowledge Retrieval — search ChromaDB for existing relevant evidence."""

from __future__ import annotations

import logging
from typing import Any

from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import PhaseToolResult

logger = logging.getLogger(__name__)


async def run_knowledge_retrieval(
    store,
    run_id: str,
    topic_id: str | None,
    query: str,
    rag_store: Any = None,
    embedding_fn: Any = None,
) -> PhaseToolResult:
    """Retrieve existing relevant evidence from the RAG knowledge base.

    Returns evidence that can be reused, reducing the need for new web searches.
    If RAG is not configured, returns empty results (no-op).
    """
    existing_evidence: list[dict[str, Any]] = []

    if rag_store and embedding_fn:
        try:
            embedding = embedding_fn(query)
            results = rag_store.query(embedding, n_results=10)
            existing_evidence = [
                {
                    "evidence_id": r.get("id", ""),
                    "content": r.get("document", ""),
                    "metadata": r.get("metadata", {}),
                    "distance": r.get("distance", 0),
                }
                for r in results
            ]
            logger.info("RAG retrieval found %d relevant documents", len(existing_evidence))
        except Exception as e:
            logger.warning("RAG retrieval failed (non-blocking): %s", e)

    covered_count = len(existing_evidence)

    artifact = await complete_phase_with_artifact(
        store,
        phase_name="knowledge_retrieval",
        artifact_type="knowledge_retrieval",
        topic_id=topic_id,
        payload={
            "retrieved_count": covered_count,
            "existing_evidence": existing_evidence,
            "new_search_needed": covered_count < 2,
        },
    )

    return PhaseToolResult(artifacts=[artifact])
