from datetime import UTC, datetime, timedelta

import pytest

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import RetrievalPlan
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever


@pytest.fixture
def repo(tmp_path):
    return KnowledgeRepository(tmp_path / "knowledge.sqlite3")


def add_document(
    repo,
    *,
    source_id: str,
    attraction_id: str,
    content: str,
    fact_type: FactType,
    publish: bool = True,
    valid_to=None,
):
    result = repo.ingest(
        KnowledgeDocument(
            source_id=source_id,
            attraction=Attraction(attraction_id=attraction_id, name=attraction_id),
            url=f"https://example.test/{source_id}",
            title=source_id,
            source_type=SourceType.OFFICIAL,
            content=content,
            valid_to=valid_to,
            chunks=[FactChunkDraft(fact_type=fact_type, content=content)],
        )
    )
    if publish:
        repo.publish(result.version_id)
    return result


def plan(*, attraction="forbidden-city", fact_type=FactType.RESERVATION):
    return RetrievalPlan(
        task_type="fact_query",
        query_text="预约 入馆",
        attraction_ids=[attraction],
        fact_types=[fact_type],
        as_of=datetime.now(UTC),
        top_k=3,
        subtask_id="fact-1",
    )


def test_lexical_retrieval_applies_attraction_and_fact_filters(repo):
    expected = add_document(
        repo,
        source_id="fc-reservation",
        attraction_id="forbidden-city",
        content="预约 入馆 请提前实名预约",
        fact_type=FactType.RESERVATION,
    )
    add_document(
        repo,
        source_id="sp-reservation",
        attraction_id="summer-palace",
        content="预约 入馆 可提前预约",
        fact_type=FactType.RESERVATION,
    )
    add_document(
        repo,
        source_id="fc-hours",
        attraction_id="forbidden-city",
        content="预约 入馆 时段为九点",
        fact_type=FactType.OPENING_HOURS,
    )

    hits = SQLiteLexicalRetriever(repo).retrieve(plan(), limit=20)

    assert len(hits) == 1
    assert hits[0].document_version_id == expected.version_id


def test_lexical_retrieval_never_leaks_pending_or_expired(repo):
    add_document(
        repo,
        source_id="pending",
        attraction_id="forbidden-city",
        content="预约 入馆 尚未发布",
        fact_type=FactType.RESERVATION,
        publish=False,
    )
    add_document(
        repo,
        source_id="expired",
        attraction_id="forbidden-city",
        content="预约 入馆 历史规定",
        fact_type=FactType.RESERVATION,
        valid_to=datetime.now(UTC) - timedelta(minutes=1),
    )
    repo.expire_due()

    assert SQLiteLexicalRetriever(repo).retrieve(plan(), limit=20) == []


def test_lexical_retrieval_limit_is_bounded(repo):
    with pytest.raises(ValueError, match="20"):
        SQLiteLexicalRetriever(repo).retrieve(plan(), limit=21)
