from datetime import UTC, datetime, timedelta

import pytest

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    IndexGenerationStatus,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.repository import KnowledgeRepository


@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepository(tmp_path / "knowledge.sqlite3")


def document(content: str, *, valid_to: datetime | None = None) -> KnowledgeDocument:
    return KnowledgeDocument(
        source_id="source-forbidden-city-hours",
        attraction=Attraction(
            attraction_id="forbidden-city",
            name="故宫博物院",
            city="北京",
            country="中国",
        ),
        url="https://www.dpm.org.cn/visit/hours",
        title="故宫参观时间",
        source_type=SourceType.OFFICIAL,
        content=content,
        valid_to=valid_to,
        chunks=[
            FactChunkDraft(
                fact_type=FactType.OPENING_HOURS,
                content=content,
                locator="visit-hours",
            )
        ],
    )


def test_completing_generation_atomically_supersedes_previous_active(repo):
    first = repo.start_index_generation("corpus-1", "fake-v1")
    repo.complete_index_generation(first.generation_id, indexed_chunk_count=3)
    second = repo.start_index_generation("corpus-2", "fake-v1")

    repo.complete_index_generation(second.generation_id, indexed_chunk_count=4)

    assert repo.get_index_generation(first.generation_id).status is IndexGenerationStatus.SUPERSEDED
    assert repo.active_index_generation().generation_id == second.generation_id


def test_failed_generation_never_replaces_active_generation(repo):
    active = repo.start_index_generation("corpus-1", "fake-v1")
    repo.complete_index_generation(active.generation_id, indexed_chunk_count=3)
    failing = repo.start_index_generation("corpus-2", "fake-v1")

    repo.fail_index_generation(failing.generation_id, failure_code="qdrant_timeout")

    assert repo.get_index_generation(failing.generation_id).status is IndexGenerationStatus.FAILED
    assert repo.active_index_generation().generation_id == active.generation_id


def test_list_active_chunks_excludes_pending_and_expired_versions(repo):
    active = repo.ingest(document("开放时间 09:00-17:00"))
    repo.publish(active.version_id)
    repo.ingest(document("尚未发布的新开放时间 08:30-17:00"))
    expired = repo.ingest(
        KnowledgeDocument(
            **document("历史开放时间").model_dump(
                exclude={"source_id", "url", "valid_to"}
            ),
            source_id="source-expired",
            url="https://www.dpm.org.cn/visit/archive-hours",
            valid_to=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    repo.publish(expired.version_id)
    repo.expire_due()

    chunks = repo.list_active_chunks(datetime.now(UTC))

    assert len(chunks) == 1
    assert chunks[0].document_version_id == active.version_id
    assert chunks[0].content == "开放时间 09:00-17:00"
    assert chunks[0].source_authority == 1.0
