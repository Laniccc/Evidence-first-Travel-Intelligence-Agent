import pytest

from app.contracts.request import AgentQueryRequest
from app.main import build_runtime
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.replay import ReplayService
from tests.integration.test_online_runtime_wiring import settings, seed, transport, parameters


@pytest.mark.asyncio
@pytest.mark.parametrize("safe", [False, True])
async def test_gap_snapshot_replay_has_no_external_or_knowledge_effects(tmp_path, monkeypatch, safe):
    config = settings(tmp_path)
    repo = seed(config)
    calls = []
    service, _, resources = build_runtime(config, llm_http_client=transport(calls),
        mcp_parameters=parameters("tool_error" if safe else "baidu"))
    await resources.start()
    try:
        original = await service.query(AgentQueryRequest(query="颐和园地址"))
    finally:
        await resources.aclose()
    def forbidden(*args, **kwargs):
        raise AssertionError("external/write call during replay")
    from app.integrations.llm.client import SingleAttemptLLMClient
    from app.integrations.mcp.baidu_gap_tool import BaiduGapTool
    from app.evidence.knowledge.promotion_service import PromotionService
    from app.evidence.retrieval.index_sync import IndexSynchronizer
    for owner, method in ((SingleAttemptLLMClient, "complete"), (BaiduGapTool, "fetch_gap"),
                          (PromotionService, "promote"), (IndexSynchronizer, "rebuild")):
        monkeypatch.setattr(owner, method, forbidden)
    with repo._connect() as db:
        before = [db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("document_version", "index_sync_job")]
    store = SQLiteRunStore(config.agent_run_db_path)
    replay = await ReplayService(store).replay(query_id=original.query_id)
    assert replay.response.answer_claims == original.answer_claims
    assert replay.response.citation_report == original.citation_report
    assert replay.response.answer == original.answer
    assert replay.run.current_state == original.orchestration_summary["terminal_state"]
    assert replay.response.orchestration_summary["replay_mode"] == "artifact_snapshot"
    again = await ReplayService(store).replay(query_id=original.query_id)
    assert again.run.replay_of_run_id == original.orchestration_summary["run_id"]
    assert any(e.state == "live_gap_fill" for e in store.phase_events(replay.run.run_id))
    with repo._connect() as db:
        assert before == [db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in ("document_version", "index_sync_job")]


@pytest.mark.asyncio
async def test_incomplete_legacy_run_fails_closed_without_creating_replay(tmp_path):
    store = SQLiteRunStore(tmp_path / "r.db")
    store.start_run(run_id="old", query_id="q", session_id="s", query="q")
    with pytest.raises(ValueError, match="replay_snapshot_unavailable"):
        await ReplayService(store).replay(query_id="q")
    assert store.latest_run_for_query("q").run_id == "old"
