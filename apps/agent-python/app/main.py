"""ASGI entry point and concrete dependency composition root."""

from pathlib import Path

from qdrant_client import QdrantClient

from app.api.app_factory import create_app
from app.api.health import ReadinessProbe
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.embedding import (
    DeterministicHashEmbedding,
    FastEmbedEmbedding,
)
from app.evidence.retrieval.hybrid import HybridRetriever, QdrantDenseRetriever
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.integrations.qdrant.vector_index import QdrantVectorIndex
from app.execution.bounded_io import BoundedIO
from app.observability.debug_session import write_agent_debug_session
from app.observability.logging import get_logger
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.agent_run_service import create_agent_run_service
from app.orchestration.state_machine import TravelAgentStateMachine

_logger = get_logger("travel_agent")


def build_runtime(settings):
    repository = KnowledgeRepository(settings.knowledge_db_path)
    client = _qdrant_client(settings)
    vector_index = QdrantVectorIndex(
        client,
        collection=settings.qdrant_collection,
        dimension=settings.embedding_dimension,
    )
    embedder = (
        DeterministicHashEmbedding(settings.embedding_dimension)
        if settings.embedding_mode == "deterministic"
        else FastEmbedEmbedding(settings.embedding_model, settings.embedding_dimension)
    )
    workers = BoundedIO()
    retriever = HybridRetriever(
        repository=repository,
        lexical=SQLiteLexicalRetriever(repository),
        dense=QdrantDenseRetriever(
            repository, vector_index=vector_index, embedder=embedder
        ),
        io_runner=workers.run,
    )

    def resolve_attraction(name: str) -> str | None:
        matches = repository.find_attractions_in_text(name, limit=1)
        return matches[0].attraction_id if matches else None

    machine = TravelAgentStateMachine(
        retriever=retriever,
        attraction_resolver=resolve_attraction,
        attraction_matcher=repository.find_attractions_in_text,
        retrieval_top_k=settings.knowledge_retrieval_top_k,
        run_store=SQLiteRunStore(settings.agent_run_db_path),
        logger=_logger,
    )
    service = create_agent_run_service(
        debug_writer=write_agent_debug_session,
        logger=_logger,
        state_machine=machine,
        debug_enabled=settings.debug,
    )

    def sqlite_probe() -> bool:
        with repository._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return True

    probe = ReadinessProbe(
        sqlite_probe=sqlite_probe,
        qdrant_probe=vector_index.health,
    )
    return service, probe, RetrievalResources(workers, client)


class RetrievalResources:
    def __init__(self, workers, client):
        self.workers, self.client = workers, client

    async def aclose(self):
        await self.workers.aclose()
        self.client.close()

    def close(self):
        self.workers.close()
        self.client.close()


def _qdrant_client(settings) -> QdrantClient:
    if settings.qdrant_mode == "local":
        path = Path(settings.qdrant_local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(path))
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


app = create_app(runtime_builder=build_runtime)


__all__ = ["app", "build_runtime"]
