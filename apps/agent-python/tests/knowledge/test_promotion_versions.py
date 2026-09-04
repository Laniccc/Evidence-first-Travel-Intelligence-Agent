from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import sqlite3

import pytest

from app.evidence.knowledge.models import Attraction, FactChunkDraft, KnowledgeDocument, SourceType
from app.evidence.knowledge.repository import KnowledgeRepository


def document(**changes):
    return KnowledgeDocument(source_id="source", attraction=Attraction(attraction_id="a", name="A"),
        url="https://example.test/a", title="fixture", source_type=SourceType.STRUCTURED,
        content="same body", chunks=[FactChunkDraft(chunk_id="fixture", fact_type="general_description", content="address A")],
        **changes)


def test_immutable_versions_and_chunk_ids(tmp_path):
    repo = KnowledgeRepository(tmp_path / "k.db")
    doc = document()
    first = repo.ingest(doc)
    repo.publish(first.version_id)
    again = repo.publish(first.version_id)
    assert again == repo.publish(first.version_id)
    changed = doc.model_copy(update={"chunks": [FactChunkDraft(chunk_id="fixture", fact_type="general_description", content="address B")]})
    second = repo.ingest(changed)
    assert second.created and second.content_hash != first.content_hash
    repo.publish(second.version_id)
    with pytest.raises(ValueError, match="pending"):
        repo.publish(first.version_id)
    assert repo.get_chunk("fixture").content == "address A"
    assert len(repo.list_active_chunks(datetime.now(UTC))) == 1
    assert repo.list_active_chunks(datetime.now(UTC))[0].chunk_id != "fixture"
    ttl = repo.ingest(changed.model_copy(update={"valid_to": datetime.now(UTC) + timedelta(days=1)}))
    assert ttl.created


def test_expired_pending_cannot_publish(tmp_path):
    repo = KnowledgeRepository(tmp_path / "k.db")
    result = repo.ingest(document(valid_to=datetime.now(UTC) - timedelta(days=1)))
    with pytest.raises(ValueError, match="expired"):
        repo.publish(result.version_id)


def test_cannot_rebind_source_and_history_retains_source_metadata(tmp_path):
    repo = KnowledgeRepository(tmp_path / "k.db")
    doc = document()
    first = repo.ingest(doc)
    with pytest.raises(ValueError, match="binding"):
        repo.ingest(doc.model_copy(update={"attraction": Attraction(attraction_id="b", name="B")}))
    second = repo.ingest(doc.model_copy(update={"url": "https://example.test/new", "source_type": SourceType.OFFICIAL}))
    assert second.created
    assert repo.get_chunk("fixture").source_url == doc.url
    assert repo.get_chunk("fixture").source_type == SourceType.STRUCTURED


def test_concurrent_same_document_has_one_version_and_active(tmp_path):
    repo = KnowledgeRepository(tmp_path / "k.db")
    doc = document()
    def write(_):
        result = repo.ingest(doc)
        repo.publish(result.version_id)
        return result.version_id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(write, range(2)))
    assert len(set(ids)) == 1 and repo.count_versions("source") == 1
    assert len(repo.active_versions("a")) == 1


def test_old_schema_migrates_idempotently_without_hash_or_fts_loss(tmp_path):
    from pathlib import Path
    path = tmp_path / "old.db"
    # Build the exact pre-migration schema, then seed legacy rows directly.
    schema = Path("app/evidence/knowledge/schema.sql").read_text(encoding="utf-8").split("-- Promotion outbox")[0]
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.execute("INSERT INTO attraction VALUES ('a','A','[]',NULL,NULL,'x','x')")
        connection.execute("INSERT INTO source_document VALUES ('source','a','https://example.test/a','old','structured',0.85,'x','x')")
        connection.execute("INSERT INTO document_version(version_id,source_id,content_hash,content,status,fetched_at) VALUES ('legacy','source','legacy-hash','old','active','2026-01-01T00:00:00+00:00')")
        connection.execute("INSERT INTO fact_chunk VALUES ('legacy-chunk','legacy','a','general_description','old',NULL,'zh-CN')")
    repo = KnowledgeRepository(path)
    KnowledgeRepository(path)
    assert repo.get_version("legacy").content_hash == "legacy-hash"
    assert repo.get_version("legacy").hash_version == 1
    assert repo.get_chunk("legacy-chunk").source_url == "https://example.test/a"
    with repo._connect() as connection:
        assert connection.execute("SELECT count(*) FROM fact_chunk_fts WHERE content MATCH 'old'").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
