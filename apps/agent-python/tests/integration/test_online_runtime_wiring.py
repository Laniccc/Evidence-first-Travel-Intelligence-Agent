import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest
from mcp.client.stdio import StdioServerParameters

from app.api.app_factory import create_app
from app.config import Settings
from app.evidence.knowledge.models import Attraction, FactChunkDraft, KnowledgeDocument, SourceType
from app.evidence.knowledge.repository import KnowledgeRepository
from app.main import build_runtime
from app.orchestration.agent_core_store import SQLiteRunStore
from tests.integrations.test_stdio_session import assert_process_exited


def settings(tmp_path, **kwargs):
    return Settings(_env_file=None, knowledge_db_path=str(tmp_path / "k.db"),
        agent_run_db_path=str(tmp_path / "runs.db"), qdrant_local_path=str(tmp_path / "qdrant"),
        embedding_dimension=32, embedding_mode="deterministic", agent_runtime_profile="online",
        anthropic_api_key="fixture-only", baidu_map_ak="fixture-only",
        bounded_baidu_enabled=True, knowledge_promotion_enabled=True,
        baidu_storage_permitted=True, index_job_poll_seconds=0.05, **kwargs)


def seed(config):
    repo = KnowledgeRepository(config.knowledge_db_path)
    # Catalog-only pending document: no active address, so both real channels miss.
    repo.ingest(KnowledgeDocument(source_id="catalog", attraction=Attraction(
        attraction_id="summer-palace", name="颐和园", city="北京市"),
        url="https://example.test/catalog", title="catalog", source_type=SourceType.STRUCTURED,
        content="catalog", chunks=[FactChunkDraft(fact_type="visitor_notice", content="catalog")]))
    return repo


def parameters(mode="baidu"):
    return StdioServerParameters(command=sys.executable,
        args=[str(Path(__file__).parents[1] / "fakes" / "stdio_mcp_server.py"), mode])


def transport(calls, *, broken_candidate=False, broken_composer=False):
    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        user = payload["messages"][0]["content"]
        if "approved_claims" in user:
            claims = json.loads(user)["approved_claims"]
            text = "invalid" if broken_composer else json.dumps({"claim_order": [c["claim_id"] for c in reversed(claims)]})
        elif "untrusted_evidence" in user:
            source = json.loads(user.split("\nPrevious")[0])["untrusted_evidence"][0]
            text = "invalid" if broken_candidate else json.dumps({"candidates": [{
                "attraction_id": source["attraction_id"], "fact_type": "general_description",
                "fact_text": source["fields"]["/address"], "references": [{"evidence_id": source["evidence_id"],
                "field_path": "/address", "quote": source["fields"]["/address"]}]}]})
        else:
            text = json.dumps({"task_type": "fact_query", "rewritten_query": "颐和园地址",
                               "entities": [{"name": "颐和园"}], "fact_types": ["general_description"]})
        return httpx.Response(200, json={"id": "fixture", "type": "message", "role": "assistant",
            "model": "fixture", "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "text", "text": text}]})
    return httpx.AsyncClient(transport=httpx.MockTransport(respond))


@pytest.mark.asyncio
@pytest.mark.parametrize("broken_candidate", [False, True])
async def test_real_factory_model_gap_promotion_and_shutdown(tmp_path, broken_candidate):
    config = settings(tmp_path)
    repo = seed(config)
    calls, built = [], []
    http = transport(calls, broken_candidate=broken_candidate)
    def builder(s):
        runtime = build_runtime(s, llm_http_client=http, mcp_parameters=parameters())
        built.append(runtime[2])
        return runtime
    app = create_app(settings_override=config, runtime_builder=builder)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as web:
            response = await web.post("/agent/query", json={"query": "颐和园地址"}, headers={"X-Trace-Id": "trace-fixture"})
            assert response.status_code == 200
            body = response.json()
            assert body["orchestration_summary"]["terminal_state"] == "deliver"
            store = SQLiteRunStore(config.agent_run_db_path)
            run_id = body["orchestration_summary"]["run_id"]
            assert store.latest_state_output(run_id, "understand")["understanding_path"] == "model"
            assert store.latest_state_output(run_id, "compose")["composition_mode"] == "model"
            assert body["citation_report"]["passed"]
            gap = store.latest_state_output(run_id, "live_gap_fill")
            assert gap["tool_call_attempt_count"] == 2
            assert gap["trace_id"] == "trace-fixture"
            promoted = store.latest_state_output(run_id, "knowledge_promote")
            assert body["promotion_summary"]["status"] == ("failed" if broken_candidate else "published")
            assert body["index_sync_status"]["status"] in ({"not_applicable"} if broken_candidate else {"pending", "indexed"})
            assert promoted["resume_state"] == "compose"
            if broken_candidate:
                assert promoted["failure_code"] == "candidate_schema_invalid"
                phase = next(e for e in store.phase_events(run_id) if e.state == "knowledge_promote")
                assert phase.failure_code == "candidate_schema_invalid" and phase.status == "recovered"
                assert len(calls) == 4 and not repo.active_versions("summer-palace")
            else:
                assert promoted["results"][0]["status"] == "active" and len(calls) == 3
                job_id = promoted["results"][0]["job_id"]
                async with asyncio.timeout(5):
                    while built[0].jobs.get(job_id)["status"] != "succeeded":
                        await asyncio.sleep(0.02)
                job = built[0].jobs.get(job_id)
                assert (job["run_id"], job["query_id"], job["trace_id"]) == (run_id, body["query_id"], "trace-fixture")
            ready = (await web.get("/agent/health/ready")).json()
            assert ready["checks"]["llm"] == "configured"
            assert ready["checks"]["mcp"] == "ok"
            assert "fixture-only" not in json.dumps(body)
    resources = built[0]
    assert http.is_closed and resources.closed
    assert not resources.session.running
    assert_process_exited(resources.session)
    assert resources.coordinator.done()
    assert all(resources.workers.outstanding(lane) == 0 for lane in ("lexical", "dense", "postfilter"))
    # The persistent Qdrant lock is released, not just the session flag.
    from qdrant_client import QdrantClient
    reopened = QdrantClient(path=config.qdrant_local_path)
    reopened.close()


@pytest.mark.asyncio
async def test_offline_never_constructs_model_or_starts_stdio(tmp_path):
    config = settings(tmp_path).model_copy(update={"agent_runtime_profile": "offline"})
    seed(config)
    service, probe, resources = build_runtime(config, mcp_parameters=parameters())
    await resources.start()
    try:
        assert resources.model is None and resources.session is None and resources.coordinator is None
        assert probe.checks()["llm"] == "disabled" and probe.checks()["mcp"] == "disabled"
    finally:
        await resources.aclose()


@pytest.mark.asyncio
async def test_storage_disabled_preserves_transient_without_extraction(tmp_path):
    config = settings(tmp_path).model_copy(update={"baidu_storage_permitted": False})
    repo = seed(config)
    calls = []
    def builder(s):
        return build_runtime(s, llm_http_client=transport(calls), mcp_parameters=parameters())
    app = create_app(settings_override=config, runtime_builder=builder)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as web:
            body = (await web.post("/agent/query", json={"query": "颐和园地址"})).json()
            assert body["orchestration_summary"]["terminal_state"] == "deliver" and len(calls) == 2
            run_id = body["orchestration_summary"]["run_id"]
            artifact = SQLiteRunStore(config.agent_run_db_path).latest_state_output(run_id, "knowledge_promote")
            assert artifact["failure_code"] == "storage_not_permitted"
            with repo._connect() as db:
                assert db.execute("SELECT count(*) FROM index_sync_job").fetchone()[0] == 0
                assert db.execute("SELECT count(*) FROM document_version").fetchone()[0] == 1


@pytest.mark.parametrize("enabled", [True, False])
async def test_composer_fallback_is_audited_and_switch_disables_extra_call(tmp_path, enabled):
    from app.contracts.request import AgentQueryRequest
    config = settings(tmp_path, llm_composer_enabled=enabled)
    seed(config)
    calls = []
    service, _, resources = build_runtime(config, llm_http_client=transport(calls, broken_composer=True),
                                        mcp_parameters=parameters())
    await resources.start()
    try:
        response = await service.query(AgentQueryRequest(query="颐和园地址"))
        assert response.orchestration_summary["terminal_state"] == "deliver"
        assert response.citation_report["passed"] and response.answer_claims
        store = SQLiteRunStore(config.agent_run_db_path)
        phase = next(e for e in store.phase_events(response.orchestration_summary["run_id"]) if e.state == "compose")
        assert phase.output["composition_mode"] == "deterministic_fallback"
        assert len(calls) == (3 if enabled else 2)
        if enabled:
            assert phase.status == "recovered" and phase.failure_code == "composer_invalid_output"
        else:
            assert phase.status == "succeeded" and phase.failure_code is None
    finally:
        await resources.aclose()


@pytest.mark.asyncio
async def test_promotion_write_failure_returns_original_safe_exit_and_no_second_gap(tmp_path):
    from types import SimpleNamespace
    from app.orchestration.state_contracts import AgentState, StateContext
    from app.orchestration.states.knowledge_promotion import KnowledgePromotionHandler
    from app.orchestration.transition_table import is_allowed_transition
    from app.evidence.knowledge.candidate_extractor import CandidateExtractor
    from app.evidence.knowledge.promotion_policy import PromotionPolicy
    from tests.knowledge.test_promotion_validation import envelope, candidate, Model
    async def broken_write(*args, **kwargs):
        raise RuntimeError("secret")
    handler = KnowledgePromotionHandler(extractor=CandidateExtractor(Model([
        json.dumps({"candidates": [candidate()]})])),
        service=SimpleNamespace(validator=SimpleNamespace(policy=PromotionPolicy(storage_enabled=True)), promote=lambda: None),
        name_resolver=lambda _: "颐和园", io_runner=broken_write)
    context = StateContext(run_id="r", query_id="q", session_id="s", raw_query="q", artifacts={
        "evidence_evaluate": {"promotion_resume_state": "safe_failure"},
        "live_gap_fill": {"mcp_envelopes": [envelope().model_dump(mode="json")]}})
    result = await handler.run(context)
    assert result.next_state == AgentState.SAFE_FAILURE
    assert result.output["failure_code"] == "promotion_failed"
    assert "secret" not in result.model_dump_json()
    assert not is_allowed_transition(AgentState.KNOWLEDGE_PROMOTE, AgentState.LIVE_GAP_FILL)
    context.artifacts["knowledge_promote"] = result.output
    again = await handler.run(context)
    assert again.output["failure_code"] == "promotion_illegal_resume"


def test_offline_rejects_network_backends_before_construction(tmp_path):
    config = settings(tmp_path).model_copy(update={"agent_runtime_profile": "offline", "embedding_mode": "fastembed"})
    with pytest.raises(ValueError, match="offline_requires"):
        build_runtime(config)


@pytest.mark.asyncio
async def test_missing_credentials_reported_and_optional_mcp_failure_degrades(tmp_path):
    config = settings(tmp_path).model_copy(update={"anthropic_api_key": None, "deepseek_api_key": None,
        "baidu_map_ak": None})
    seed(config)
    _, probe, resources = build_runtime(config)
    await resources.start()
    try:
        assert probe.checks()["llm"] == "credentials_missing"
        assert probe.checks()["mcp"] == "credentials_missing"
    finally:
        await resources.aclose()
    config = config.model_copy(update={"baidu_map_ak": "fixture-only"})
    _, probe, resources = build_runtime(config, mcp_parameters=parameters("schema_large"))
    await resources.start()
    try:
        assert probe.checks()["mcp"] == "unavailable"
    finally:
        await resources.aclose()
