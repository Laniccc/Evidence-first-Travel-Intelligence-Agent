"""ASGI entry point and concrete dependency composition root."""

from pathlib import Path
import asyncio
import json

from mcp.client.stdio import StdioServerParameters

from qdrant_client import QdrantClient

from app.api.app_factory import create_app
from app.api.health import ReadinessProbe
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.knowledge.candidate_extractor import CandidateExtractor
from app.evidence.knowledge.promotion_validator import PromotionValidator
from app.evidence.knowledge.promotion_policy import PromotionPolicy
from app.evidence.knowledge.promotion_service import PromotionService
from app.evidence.knowledge.index_jobs import IndexJobs
from app.evidence.retrieval.index_sync import IndexSynchronizer
from app.evidence.retrieval.embedding import (
    DeterministicHashEmbedding,
    FastEmbedEmbedding,
)
from app.evidence.retrieval.hybrid import HybridRetriever, QdrantDenseRetriever
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.integrations.qdrant.vector_index import QdrantVectorIndex
from app.integrations.llm.client import SingleAttemptLLMClient
from app.composition.llm_composer import BoundedLLMComposer
from app.integrations.mcp.stdio_session import BoundedStdioSession
from app.integrations.mcp.baidu_gap_tool import BaiduGapTool
from app.contracts.baidu import BaiduPoiBinding
from app.understanding.primary_understanding import PrimaryUnderstandingAdapter
from app.orchestration.states.knowledge_promotion import KnowledgePromotionHandler
from app.execution.bounded_io import BoundedIO
from app.observability.debug_session import write_agent_debug_session
from app.observability.logging import get_logger
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.agent_run_service import create_agent_run_service
from app.orchestration.state_machine import TravelAgentStateMachine

_logger = get_logger("travel_agent")


def build_runtime(settings, *, llm_http_client=None, mcp_parameters=None):
    if settings.agent_runtime_profile == "offline" and (settings.qdrant_mode != "local" or settings.embedding_mode != "deterministic"):
        raise ValueError("offline_requires_local_qdrant_and_deterministic_embedding")
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

    def binding(attraction_id):
        try:
            row = repository.inspect_attraction(attraction_id)["attraction"]
        except KeyError:
            return None
        if not row["city"]:
            return None
        return BaiduPoiBinding(attraction_id=attraction_id, name=row["name"], city=row["city"],
                               aliases=tuple(json.loads(row["aliases_json"])))

    resources = RetrievalResources(workers, client)
    resources.poll_seconds = settings.index_job_poll_seconds
    resources.vector_index = vector_index
    primary, gap, promotion = None, None, None
    if settings.agent_runtime_profile == "online":
        if settings.llm_api_key():
            resources.model = SingleAttemptLLMClient(settings, http_client=llm_http_client)
            resources.llm_status = "configured"
            primary = PrimaryUnderstandingAdapter(resources.model, max_tokens=settings.understanding_max_tokens)
        else:
            resources.llm_status = "credentials_missing"
        if settings.bounded_baidu_enabled:
            resources.mcp_status = "credentials_missing"
            if settings.baidu_map_ak:
                entrypoint = Path(settings.bounded_baidu_server_entrypoint) if settings.bounded_baidu_server_entrypoint else (
                    Path(__file__).resolve().parents[3] / "infra/baidu-mcp/node_modules/@baidumap/mcp-server-baidu-map/dist/index.js")
                if mcp_parameters is not None or entrypoint.is_file():
                    params = mcp_parameters or StdioServerParameters(
                        command=settings.bounded_baidu_node, args=[str(entrypoint.resolve())],
                        env={"BAIDU_MAP_API_KEY": settings.baidu_map_ak})
                    resources.session = BoundedStdioSession(params)
                    resources.mcp_status = "starting"
                    gap = BaiduGapTool(resources.session, binding_resolver=binding)
                else:
                    resources.mcp_status = "configuration_missing"
        resources.jobs = IndexJobs(repository, IndexSynchronizer(repository, vector_index=vector_index, embedder=embedder))
        if settings.knowledge_promotion_enabled and resources.model is not None:
            promotion = KnowledgePromotionHandler(extractor=CandidateExtractor(resources.model),
                service=PromotionService(repository, PromotionValidator(PromotionPolicy(
                    storage_enabled=settings.baidu_storage_permitted))),
                name_resolver=lambda attraction_id: repository.inspect_attraction(attraction_id)["attraction"]["name"],
                io_runner=workers.run)

    async def read_index_job(job_id):
        return await workers.run("postfilter", resources.jobs.get, job_id) if resources.jobs else None

    machine = TravelAgentStateMachine(
        retriever=retriever,
        attraction_resolver=resolve_attraction,
        attraction_matcher=repository.find_attractions_in_text,
        retrieval_top_k=settings.knowledge_retrieval_top_k,
        primary_understanding=primary,
        understanding_timeout_seconds=settings.understanding_timeout_seconds,
        composer=BoundedLLMComposer(resources.model) if resources.model and settings.llm_composer_enabled else None,
        composer_timeout_seconds=settings.composer_timeout_seconds,
        gap_tool=gap,
        promotion_handler=promotion,
        index_job_reader=read_index_job,
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
        qdrant_probe=lambda: resources.qdrant_ready,
        runtime_checks=resources.checks,
    )
    return service, probe, resources


class RetrievalResources:
    def __init__(self, workers, client):
        self.workers, self.client = workers, client
        self.model = self.session = self.jobs = self.coordinator = None
        self.llm_status = self.mcp_status = "disabled"
        self.vector_index = None
        self.qdrant_ready = False
        self.closed = False
        self._stop = asyncio.Event()
        self.poll_seconds = 5

    def checks(self):
        mcp = self.mcp_status
        if mcp == "ok" and self.session and not self.session.running:
            mcp = "unavailable"
        return {"llm": self.llm_status, "mcp": mcp,
                "index_coordinator": "running" if self.coordinator and not self.coordinator.done() else "disabled"}

    def _refresh_index_health(self):
        try:
            self.qdrant_ready = bool(self.vector_index.health())
        except Exception:
            self.qdrant_ready = False

    async def start(self):
        if self.session:
            try:
                await self.session.__aenter__()
                self.mcp_status = "ok"
            except Exception:
                self.mcp_status = "unavailable"
        await self.workers.run("dense", self._refresh_index_health)
        if self.jobs:
            self.coordinator = asyncio.create_task(self._coordinate(), name="travel-index-coordinator")

    async def _coordinate(self):
        while not self._stop.is_set():
            try:
                # Same serial lane as retrieval; no concurrent Qdrant local access.
                await self.workers.run("dense", self.jobs.run_pending, limit=1)
                await self.workers.run("dense", self._refresh_index_health)
            except Exception:
                self.qdrant_ready = False
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def aclose(self):
        if self.closed:
            return
        self._stop.set()
        try:
            if self.coordinator:
                await self.coordinator
        finally:
            try:
                if self.session:
                    await self.session.aclose()
            finally:
                try:
                    if self.model:
                        await self.model.aclose()
                finally:
                    await self.workers.aclose()
                    self.client.close()
                    self.closed = True

    def close(self):
        if self.model or self.session or self.coordinator:
            raise RuntimeError("Online resources require awaited aclose")
        self.workers.close()
        self.client.close()
        self.closed = True


def _qdrant_client(settings) -> QdrantClient:
    if settings.qdrant_mode == "local":
        path = Path(settings.qdrant_local_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(path))
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


app = create_app(runtime_builder=build_runtime)


__all__ = ["app", "build_runtime"]
