import pytest

from app.config import Settings
from app.contracts.request import AgentQueryRequest
from app.evidence.knowledge.models import Attraction, FactChunkDraft, FactType, KnowledgeDocument, SourceType
from app.evidence.knowledge.repository import KnowledgeRepository
from app.main import build_runtime
from app.orchestration.agent_core_store import SQLiteRunStore


@pytest.mark.asyncio
async def test_production_factory_passes_operator_top_k_and_persists_natural_query_plan(tmp_path):
    settings = Settings(
        _env_file=None, knowledge_retrieval_top_k=50, embedding_mode="deterministic",
        knowledge_db_path=str(tmp_path / "knowledge.sqlite3"),
        agent_run_db_path=str(tmp_path / "runs.sqlite3"),
        qdrant_mode="local", qdrant_local_path=str(tmp_path / "qdrant"),
    )
    repo = KnowledgeRepository(settings.knowledge_db_path)
    ingested = repo.ingest(KnowledgeDocument(
        source_id="official", attraction=Attraction(
            attraction_id="palace", name="故宫博物院", aliases=["故宫"]),
        url="https://example.test/hours", title="开放时间", source_type=SourceType.OFFICIAL,
        content="开放时间：08:30—17:00",
        chunks=[FactChunkDraft(fact_type=FactType.OPENING_HOURS, content="开放时间：08:30—17:00")],
    ))
    repo.publish(ingested.version_id)
    service, _, client = build_runtime(settings)
    try:
        response = await service.query(AgentQueryRequest(query="故宫几点开门"))
        assert response.orchestration_summary["terminal_state"] == "deliver"
        store = SQLiteRunStore(settings.agent_run_db_path)
        run_id = store.inspect(response.query_id).run.run_id
        plan = store.latest_state_output(run_id, "retrieval_plan")["retrieval_plans"][0]
        assert plan["top_k"] == 5
        assert plan["raw_query"] == "故宫几点开门"
        assert "开放时间" in plan["lexical_query"]
        understanding = store.latest_state_output(run_id, "understand")
        assert understanding["understanding_path"] == "rule"  # LLM wiring belongs to Task 10.
    finally:
        client.close()
