from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
    VersionStatus,
)
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.knowledge.service import KnowledgeLifecycleService


def _document(source_type: SourceType, *, url: str = "https://example.test/place"):
    return KnowledgeDocument(
        source_id=f"source-{source_type.value}",
        attraction=Attraction(
            attraction_id="summer-palace",
            name="颐和园",
            aliases=["Summer Palace"],
            city="北京",
            country="中国",
        ),
        url=url,
        title="颐和园参观须知",
        source_type=source_type,
        content="旺季开放时间为 06:00-20:00，请以当日公告为准。",
        chunks=[
            FactChunkDraft(
                fact_type=FactType.OPENING_HOURS,
                content="旺季开放时间为 06:00-20:00。",
                locator="hours",
            )
        ],
    )


def test_official_valid_document_can_auto_publish(tmp_path):
    repo = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    service = KnowledgeLifecycleService(repo)

    result = service.ingest(_document(SourceType.OFFICIAL), auto_publish=True)

    assert repo.get_version(result.version_id).status is VersionStatus.ACTIVE


def test_untrusted_source_stays_pending_even_when_auto_publish_requested(tmp_path):
    repo = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    service = KnowledgeLifecycleService(repo)

    result = service.ingest(_document(SourceType.FORUM), auto_publish=True)

    assert repo.get_version(result.version_id).status is VersionStatus.PENDING


def test_non_https_document_fails_deterministic_publish_validation(tmp_path):
    repo = KnowledgeRepository(tmp_path / "knowledge.sqlite3")
    service = KnowledgeLifecycleService(repo)

    result = service.ingest(
        _document(SourceType.OFFICIAL, url="http://example.test/place"),
        auto_publish=True,
    )

    version = repo.get_version(result.version_id)
    assert version.status is VersionStatus.REJECTED
    assert "https" in (version.rejection_reason or "")
