"""Phase 6: Knowledge Upsert — store evidence in ChromaDB for future reuse."""

from __future__ import annotations

import logging
from typing import Any

from app.agent_core.phases.common import complete_phase_with_artifact
from app.agent_core.state.models import PhaseToolResult

logger = logging.getLogger(__name__)


async def run_knowledge_upsert(
    store,
    run_id: str | None = None,
    topic_id: str | None = None,
    evidence_records: list[Any] | None = None,
    rag_store: Any = None,
    embedding_fn: Any = None,
) -> PhaseToolResult:
    """Store newly acquired evidence in the RAG knowledge base."""
    evidence_records = evidence_records or []
    upserted = 0

    if rag_store and embedding_fn:
        for ev in evidence_records:
            try:
                claims_text = " ".join(
                    c.get("claim", str(c)) if isinstance(c, dict) else str(c)
                    for c in (getattr(ev, "claims", []) or [])
                )
                if len(claims_text.strip()) < 20:
                    snippet = getattr(ev, "raw_payload", {}).get("snippet", "")
                    claims_text = str(snippet) if snippet else ""

                if len(claims_text.strip()) < 20:
                    continue

                embedding = embedding_fn(claims_text[:2000])
                if embedding is None:
                    continue

                rag_store.add(
                    embeddings=[embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)],
                    documents=[claims_text[:2000]],
                    metadatas=[{
                        "source_url": str(getattr(ev, "source_url", "")),
                        "source_name": getattr(ev, "source_name", ""),
                        "source_tier": getattr(ev, "source_tier", 3),
                        "topic_id": topic_id or "",
                    }],
                    ids=[getattr(ev, "evidence_id", "ev_unknown")],
                )
                upserted += 1
            except Exception as e:
                logger.warning("RAG upsert failed for %s: %s", getattr(ev, "evidence_id", "?"), e)

    artifact = await complete_phase_with_artifact(
        store, phase_name="knowledge_upsert", topic_id=topic_id,
        artifact_type="knowledge_upsert",
        payload={"upserted_count": upserted, "total": len(evidence_records)},
    )
    return PhaseToolResult(artifacts=[artifact])
