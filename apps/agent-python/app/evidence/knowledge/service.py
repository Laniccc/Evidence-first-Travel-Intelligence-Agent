"""Deterministic publication policy for attraction knowledge."""

from app.evidence.knowledge.models import (
    IngestResult,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.repository import KnowledgeRepository


AUTO_PUBLISH_SOURCE_TYPES = frozenset({SourceType.OFFICIAL, SourceType.STRUCTURED})


class KnowledgeLifecycleService:
    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def ingest(
        self,
        document: KnowledgeDocument,
        *,
        auto_publish: bool = False,
    ) -> IngestResult:
        result = self.repository.ingest(document)
        if not auto_publish or document.source_type not in AUTO_PUBLISH_SOURCE_TYPES:
            return result
        error = self._validation_error(document)
        if error:
            self.repository.reject(result.version_id, reason=error)
        else:
            self.repository.publish(result.version_id)
        version = self.repository.get_version(result.version_id)
        return result.model_copy(update={"status": version.status})

    @staticmethod
    def _validation_error(document: KnowledgeDocument) -> str | None:
        if not document.url.startswith("https://"):
            return "source URL must use https"
        if not document.content.strip():
            return "document content is empty"
        if not document.chunks:
            return "document has no fact chunks"
        if any(not chunk.content.strip() for chunk in document.chunks):
            return "fact chunk content is empty"
        return None
