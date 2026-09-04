from datetime import UTC, datetime, timedelta

import pytest

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
    VersionStatus,
)
from app.evidence.knowledge.repository import KnowledgeRepository


ATTRACTION_ID = "forbidden-city"
URL = "https://www.dpm.org.cn/visit/hours"


@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepository(tmp_path / "knowledge.sqlite3")


def document(content: str, *, valid_to: datetime | None = None) -> KnowledgeDocument:
    return KnowledgeDocument(
        source_id="source-forbidden-city-hours",
        attraction=Attraction(
            attraction_id=ATTRACTION_ID,
            name="故宫博物院",
            aliases=["故宫", "Forbidden City"],
            city="北京",
            country="中国",
        ),
        url=URL,
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


def test_publish_supersedes_previous_active_version(repo):
    first = repo.ingest(document("开放时间 09:00-17:00"))
    repo.publish(first.version_id)
    second = repo.ingest(document("开放时间 08:30-17:00"))
    repo.publish(second.version_id)

    assert repo.get_version(first.version_id).status is VersionStatus.SUPERSEDED
    assert repo.get_version(second.version_id).status is VersionStatus.ACTIVE
    assert [item.version_id for item in repo.active_versions(ATTRACTION_ID)] == [
        second.version_id
    ]


def test_same_hash_is_idempotent(repo):
    first = repo.ingest(document("开放时间 09:00-17:00"))
    second = repo.ingest(document("开放时间 09:00-17:00"))

    assert first.created is True
    assert second.created is False
    assert second.version_id == first.version_id
    assert repo.count_versions(first.source_id) == 1


def test_expired_version_is_not_active(repo):
    result = repo.ingest(
        document(
            "暑期开放时间 08:30-17:00",
            valid_to=datetime.now(UTC) - timedelta(minutes=1),
        )
    )
    historical = KnowledgeRepository(repo.db_path, clock=lambda: datetime.now(UTC) - timedelta(days=1))
    historical.publish(result.version_id)

    expired_count = repo.expire_due(datetime.now(UTC))

    assert expired_count == 1
    assert repo.get_version(result.version_id).status is VersionStatus.EXPIRED
    assert repo.active_versions(ATTRACTION_ID) == []


def test_rejected_version_cannot_be_published(repo):
    result = repo.ingest(document("开放时间未知"))
    repo.reject(result.version_id, reason="failed deterministic validation")

    with pytest.raises(ValueError, match="rejected"):
        repo.publish(result.version_id)
