from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from qdrant_client import QdrantClient

from app.evidence.knowledge.index_jobs import IndexJobs
from app.evidence.knowledge.promotion_service import PromotionService
from app.evidence.knowledge.promotion_policy import PromotionPolicy
from app.evidence.knowledge.promotion_validator import PromotionValidator
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.embedding import DeterministicHashEmbedding
from app.evidence.retrieval.index_sync import IndexSynchronizer, IndexSyncError
from app.integrations.qdrant.vector_index import QdrantVectorIndex
from tests.knowledge.test_promotion_validation import candidate, envelope
from tests.knowledge.test_promotion_versions import document


def service(repo):
    return PromotionService(repo, PromotionValidator(PromotionPolicy(storage_enabled=True)))


def promote(svc):
    return svc.promote(candidate(), [envelope(retrieved_at=datetime.now(UTC))], name="颐和园",
        run_id="run", query_id="query", trace_id="trace")


def test_publish_and_enqueue_rollback_together(tmp_path):
    repo = KnowledgeRepository(tmp_path / "k.db")
    svc = service(repo)
    with patch.object(svc, "_enqueue", side_effect=RuntimeError("fault after publish")):
        with pytest.raises(RuntimeError):
            promote(svc)
    with repo._connect() as db:
        for table in ("document_version", "promotion_decision", "index_sync_job", "fact_chunk_fts"):
            assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


@pytest.fixture
def sync(tmp_path):
    repo = KnowledgeRepository(tmp_path / "k.db")
    client = QdrantClient(path=str(tmp_path / "qdrant"))
    index = QdrantVectorIndex(client, collection="facts", dimension=32)
    synchronizer = IndexSynchronizer(repo, vector_index=index, embedder=DeterministicHashEmbedding(32))
    yield repo, index, synchronizer
    client.close()


def test_durable_retry_restart_and_idempotency(sync):
    repo, index, synchronizer = sync
    result = promote(service(repo))
    assert result["status"] == "active" and result["job_id"]
    jobs = IndexJobs(repo, synchronizer)
    with patch.object(index, "upsert", side_effect=TimeoutError("secret")):
        assert jobs.run_pending(limit=10)[0]["status"] == "pending"
    job = jobs.get(result["job_id"])
    assert job["attempts"] == 1 and job["last_failure_code"] and "secret" not in str(job)
    assert repo.active_versions("summer-palace")
    restarted = IndexJobs(KnowledgeRepository(repo.db_path), synchronizer,
        clock=lambda: datetime.now(UTC) + timedelta(seconds=60))
    assert restarted.run_pending(limit=10)[0]["status"] == "succeeded"
    assert restarted.run_pending(limit=10) == []
    assert repo.count_versions(repo.get_version(result["version_id"]).source_id) == 1
    assert jobs.get(result["job_id"])["trace_id"] == "trace"


def test_same_source_writers_and_exhausted_attempts(sync):
    repo, index, synchronizer = sync
    env = envelope(retrieved_at=datetime.now(UTC))
    svc = service(repo)
    def write(_):
        return svc.promote(candidate(), [env], name="颐和园", run_id="run", query_id="query", trace_id="trace")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, range(2)))
    assert len({r["version_id"] for r in results}) == 1
    assert len({r["job_id"] for r in results}) == 1
    for n in range(3):
        jobs = IndexJobs(repo, synchronizer, clock=lambda: datetime.now(UTC) + timedelta(minutes=n))
        with patch.object(index, "upsert", side_effect=TimeoutError()):
            jobs.run_pending(limit=10)
    assert jobs.get(results[0]["job_id"])["status"] == "failed"
    assert jobs.get(results[0]["job_id"])["attempts"] == 3


def test_reused_generation_is_verified_and_never_deleted(sync):
    repo, index, synchronizer = sync
    promote(service(repo))
    corpus = repo.compute_corpus_version()
    first = synchronizer.rebuild(corpus_version=corpus)
    chunks = repo.list_active_chunks(datetime.now(UTC))
    index.delete([chunks[0].chunk_id], corpus_version=corpus, embedding_model=synchronizer.embedder.model_name)
    repaired = synchronizer.rebuild(corpus_version=corpus)
    assert not repaired.reused and repaired.generation_id != first.generation_id
    assert index.count() == 1  # Do not delete repaired same-corpus point IDs.


def test_corpus_drift_does_not_activate_generation(sync):
    repo, index, synchronizer = sync
    promote(service(repo))
    original = index.upsert
    def drift(points):
        original(points)
        result = repo.ingest(document())
        repo.publish(result.version_id)
    with patch.object(index, "upsert", side_effect=drift):
        with pytest.raises(IndexSyncError, match="corpus_drift"):
            synchronizer.rebuild(corpus_version=repo.compute_corpus_version())
    assert repo.active_index_generation() is None


def test_cleanup_failure_is_observable_without_losing_active(sync):
    repo, index, synchronizer = sync
    promote(service(repo))
    synchronizer.rebuild(corpus_version=repo.compute_corpus_version())
    doc = repo.ingest(document())
    repo.publish(doc.version_id)
    with patch.object(index, "delete", side_effect=TimeoutError()):
        result = synchronizer.rebuild(corpus_version=repo.compute_corpus_version())
    assert result.status == "active" and result.cleanup_failure_code == "timeout"
    assert repo.active_index_generation().generation_id == result.generation_id


def test_expired_lease_is_recovered_once_and_cli_status(sync):
    from app.evidence.knowledge.cli import main
    repo, index, synchronizer = sync
    result = promote(service(repo))
    jobs = IndexJobs(repo, synchronizer)
    claimed = jobs._claim()
    assert claimed["job_id"] == result["job_id"] and jobs._claim() is None
    restarted = IndexJobs(repo, synchronizer, clock=lambda: datetime.now(UTC) + timedelta(minutes=6))
    assert restarted.run_pending(limit=1)[0]["status"] == "succeeded"
    assert jobs.get(result["job_id"])["attempts"] == 2
    # CLI does not touch Qdrant if no job is due; failed jobs remain a nonzero exit.
    with repo._connect() as db:
        db.execute("UPDATE index_sync_job SET status='failed'")
    assert main(["sync-pending", "--db", str(repo.db_path), "--qdrant-path", str(repo.db_path.parent / "cli-qdrant"), "--limit", "1"]) == 1


def test_vector_payload_corruption_not_hidden_by_correct_count(sync):
    repo, index, synchronizer = sync
    promote(service(repo))
    corpus = repo.compute_corpus_version()
    first = synchronizer.rebuild(corpus_version=corpus)
    chunk = repo.list_active_chunks(datetime.now(UTC))[0]
    point_id = index.point_id(f"{corpus}:{synchronizer.embedder.model_name}:{chunk.chunk_id}")
    index.client.set_payload(index.collection, {"content_hash": "wrong"}, points=[point_id])
    repaired = synchronizer.rebuild(corpus_version=corpus)
    assert repaired.generation_id != first.generation_id and not repaired.reused
    assert index.verify_generation([chunk], corpus_version=corpus, embedding_model=synchronizer.embedder.model_name)
