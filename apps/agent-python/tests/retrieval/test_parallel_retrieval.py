import asyncio
import threading

import pytest

from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.hybrid import HybridRetriever
from app.execution.bounded_io import BoundedIO, WorkerBusy
from tests.fakes.failing_retrievers import plan
from tests.retrieval.test_hybrid import seeded_repo, make_plan


@pytest.mark.asyncio
async def test_persisted_qdrant_dense_lane_and_comparison_artifacts(seeded_repo, tmp_path):
    from qdrant_client import QdrantClient
    from app.evidence.retrieval.embedding import DeterministicHashEmbedding
    from app.evidence.retrieval.hybrid import QdrantDenseRetriever
    from app.evidence.retrieval.index_sync import IndexSynchronizer
    from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
    from app.integrations.qdrant.vector_index import QdrantVectorIndex

    client = QdrantClient(path=str(tmp_path / "qdrant"))
    index = QdrantVectorIndex(client, collection="test", dimension=32)
    embedder = DeterministicHashEmbedding(32)
    IndexSynchronizer(seeded_repo, vector_index=index, embedder=embedder).rebuild(corpus_version="async-test")
    io = BoundedIO()
    retriever = HybridRetriever(repository=seeded_repo, lexical=SQLiteLexicalRetriever(seeded_repo),
                                dense=QdrantDenseRetriever(seeded_repo, vector_index=index, embedder=embedder),
                                io_runner=io.run)
    try:
        results = await asyncio.gather(
            retriever.aretrieve(make_plan(subtask_id="left")),
            retriever.aretrieve(make_plan(subtask_id="right")),
        )
        assert [r.subtask_id for r in results] == ["left", "right"]
        assert all(r.dense_attempt.status == "success" and r.final_hits for r in results)
        assert all("dense" in h.retrieval_channels for r in results for h in r.final_hits)
    finally:
        await io.aclose()
        client.close()


@pytest.mark.asyncio
async def test_channels_reach_barrier_together(tmp_path):
    entered = [asyncio.Event(), asyncio.Event()]
    release = asyncio.Event()

    class Channel:
        def __init__(self, index):
            self.index = index

        async def aretrieve(self, request, *, limit):
            entered[self.index].set()
            await release.wait()
            return []

    io = BoundedIO()
    retriever = HybridRetriever(repository=KnowledgeRepository(tmp_path / "kb.db"),
                                lexical=Channel(0), dense=Channel(1), io_runner=io.run)
    task = asyncio.create_task(retriever.aretrieve(plan()))
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in entered)), 2)
        assert not task.done()
        release.set()
        result = await task
        assert result.degradation == "no_results"
    finally:
        release.set()
        await io.aclose()


@pytest.mark.asyncio
async def test_timeout_releases_async_channel_but_preserves_other_channel(tmp_path):
    cancelled = asyncio.Event()

    class Slow:
        async def aretrieve(self, *args, **kwargs):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    class Empty:
        async def aretrieve(self, *args, **kwargs):
            return []

    io = BoundedIO()
    retriever = HybridRetriever(repository=KnowledgeRepository(tmp_path / "kb.db"),
                                lexical=Empty(), dense=Slow(), io_runner=io.run,
                                channel_timeout_seconds=0.02)
    try:
        result = await retriever.aretrieve(plan())
        assert result.degradation == "lexical_only"
        assert result.dense_attempt.failure_code == "timeout"
        assert result.lexical_attempt.status == "empty"
        assert cancelled.is_set()
    finally:
        await io.aclose()


@pytest.mark.asyncio
async def test_sync_timeout_retains_capacity_until_actual_worker_completion():
    started = threading.Event()
    release = threading.Event()
    io = BoundedIO(capacity_per_lane=1)

    def slow():
        started.set()
        release.wait(5)

    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(io.run("dense", slow), 0.1)
        assert started.is_set()
        assert io.outstanding("dense") == 1
        with pytest.raises(WorkerBusy):
            await io.run("dense", lambda: None)
        release.set()
        await io.aclose()
        assert io.outstanding("dense") == 0
    finally:
        release.set()
        await io.aclose()


@pytest.mark.asyncio
async def test_parent_cancellation_cancels_both_channels(tmp_path):
    entered, cancelled = [asyncio.Event(), asyncio.Event()], [asyncio.Event(), asyncio.Event()]

    class Channel:
        def __init__(self, index):
            self.index = index

        async def aretrieve(self, *args, **kwargs):
            entered[self.index].set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled[self.index].set()

    io = BoundedIO()
    retriever = HybridRetriever(repository=KnowledgeRepository(tmp_path / "kb.db"),
                                lexical=Channel(0), dense=Channel(1), io_runner=io.run)
    task = asyncio.create_task(retriever.aretrieve(plan()))
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in entered)), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert all(e.is_set() for e in cancelled)
    finally:
        await io.aclose()


@pytest.mark.asyncio
async def test_both_failures_are_independently_reported(tmp_path):
    class Broken:
        async def aretrieve(self, *args, **kwargs):
            raise TimeoutError("must not log provider secrets")

    io = BoundedIO()
    retriever = HybridRetriever(repository=KnowledgeRepository(tmp_path / "kb.db"),
                                lexical=Broken(), dense=Broken(), io_runner=io.run)
    try:
        result = await retriever.aretrieve(plan())
        assert result.degradation == "all_failed"
        assert result.lexical_attempt.failure_code == result.dense_attempt.failure_code == "timeout"
        assert "secrets" not in result.model_dump_json()
    finally:
        await io.aclose()
