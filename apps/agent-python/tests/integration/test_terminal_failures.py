from unittest.mock import patch

import pytest

from app.config import Settings
from app.contracts.request import AgentQueryRequest
from app.main import build_runtime
from app.orchestration.agent_core_store import SQLiteRunStore
from tests.integration.test_batch_a_runtime import KnowledgeDocument, Attraction, FactChunkDraft, FactType, SourceType, KnowledgeRepository


def runtime(tmp_path):
    s = Settings(_env_file=None, knowledge_db_path=str(tmp_path / "k.db"), agent_run_db_path=str(tmp_path / "r.db"), qdrant_local_path=str(tmp_path / "q"))
    repo = KnowledgeRepository(s.knowledge_db_path)
    v = repo.ingest(KnowledgeDocument(source_id="source", attraction=Attraction(attraction_id="a", name="故宫"),
        url="https://example.test/a", title="hours", source_type=SourceType.OFFICIAL, content="每日九点开门",
        chunks=[FactChunkDraft(fact_type=FactType.OPENING_HOURS, content="开放时间 每日九点开门")]))
    repo.publish(v.version_id)
    service, _, resources = build_runtime(s)
    return s, service, resources


@pytest.mark.asyncio
async def test_projection_failure_is_terminal_and_audited(tmp_path):
    s, service, resources = runtime(tmp_path)
    try:
        with patch.object(service._state_machine._delivery, "build_response", side_effect=RuntimeError("secret")):
            result = await service.query(AgentQueryRequest(query="故宫开放时间"))
        assert result.orchestration_summary["terminal_state"] == "failed"
        assert result.answer_claims == [] and "secret" not in result.model_dump_json()
        record = SQLiteRunStore(s.agent_run_db_path).inspect(result.query_id)
        assert record.run.status == "failed"
        assert any(e.failure_code == "terminal_projection_failed" for e in SQLiteRunStore(s.agent_run_db_path).phase_events(record.run.run_id))
    finally:
        await resources.aclose()


@pytest.mark.asyncio
async def test_audit_write_failure_cannot_return_success(tmp_path):
    _, service, resources = runtime(tmp_path)
    try:
        with patch.object(service._state_machine._run_store, "append_phase_event", side_effect=RuntimeError("secret")):
            with pytest.raises(RuntimeError, match="audit_persistence_unavailable"):
                await service.query(AgentQueryRequest(query="故宫开放时间"))
    finally:
        await resources.aclose()
