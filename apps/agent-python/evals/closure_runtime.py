"""Offline transport fixtures exercising the real composition root, never real providers."""
import asyncio
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from unittest.mock import patch

import httpx
from mcp.client.stdio import StdioServerParameters

from app.config import Settings
from app.contracts.request import AgentQueryRequest
from app.contracts.mcp_evidence import McpEvidenceEnvelope
from app.evidence.knowledge.models import Attraction, FactChunkDraft, KnowledgeDocument
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.knowledge.promotion_service import PromotionService
from app.evidence.knowledge.promotion_validator import PromotionValidator
from app.evidence.knowledge.promotion_policy import PromotionPolicy
from app.evidence.knowledge.index_jobs import IndexJobs
from app.evidence.retrieval.index_sync import IndexSynchronizer
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.integrations.llm.client import SingleAttemptLLMClient
from app.integrations.mcp.baidu_gap_tool import BaiduGapTool
from app.integrations.mcp.stdio_session import BoundedStdioSession
from app.main import build_runtime
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.replay import ReplayService


def parameters(mode="baidu"):
    return StdioServerParameters(command=sys.executable, args=[
        str(Path(__file__).parents[1] / "tests/fakes/stdio_mcp_server.py"), mode])


def fixture_settings(directory):
    return Settings(_env_file=None, knowledge_db_path=str(directory / "knowledge.db"),
        agent_run_db_path=str(directory / "runs.db"), qdrant_local_path=str(directory / "qdrant"),
        embedding_dimension=32, embedding_mode="deterministic", agent_runtime_profile="online",
        qdrant_mode="local", qdrant_collection="closure-fixture", qdrant_api_key=None, debug=False,
        anthropic_base_url="https://fixture.invalid", anthropic_model="fixture", deepseek_model="fixture",
        anthropic_api_key="fixture-only", deepseek_api_key=None, baidu_map_ak="fixture-only",
        bounded_baidu_enabled=True, knowledge_promotion_enabled=True,
        baidu_storage_permitted=True, index_job_poll_seconds=0.05)


def fixture_transport(calls):
    def respond(request):
        payload = json.loads(request.content)
        calls.append(payload)
        user = payload["messages"][0]["content"]
        if "approved_claims" in user:
            text = json.dumps({"claim_order": [c["claim_id"] for c in reversed(json.loads(user)["approved_claims"])]})
        elif "untrusted_evidence" in user:
            source = json.loads(user.split("\nPrevious")[0])["untrusted_evidence"][0]
            text = json.dumps({"candidates": [{
                "attraction_id": source["attraction_id"], "fact_type": "general_description",
                "fact_text": source["fields"]["/address"], "references": [{
                    "evidence_id": source["evidence_id"], "field_path": "/address",
                    "quote": source["fields"]["/address"]}]}]})
        else:
            text = json.dumps({"task_type": "fact_query", "rewritten_query": "颐和园地址",
                "entities": [{"name": "颐和园"}], "fact_types": ["general_description"]})
        return httpx.Response(200, json={"id": "fixture", "type": "message", "role": "assistant",
            "model": "fixture", "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "text", "text": text}]})
    return httpx.AsyncClient(transport=httpx.MockTransport(respond))


def knowledge_counts(repo):
    with repo._connect() as db:
        return tuple(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                     for table in ("document_version", "index_sync_job", "promotion_decision"))


async def run_dense_closure(directory):
    config = fixture_settings(directory)
    repo = KnowledgeRepository(config.knowledge_db_path)
    repo.ingest(KnowledgeDocument(source_id="catalog", attraction=Attraction(
        attraction_id="summer-palace", name="颐和园", city="北京市"),
        url="https://example.test/catalog", title="catalog", source_type="structured",
        content="catalog", chunks=[FactChunkDraft(fact_type="visitor_notice", content="catalog")]))
    calls = []
    service, _, resources = build_runtime(config, llm_http_client=fixture_transport(calls),
                                         mcp_parameters=parameters())
    store = SQLiteRunStore(config.agent_run_db_path)
    result = {}
    try:
        # Fault only the vector write channel; the transaction/outbox and worker are real.
        with patch.object(resources.vector_index, "upsert", side_effect=TimeoutError("eval outage")):
            await resources.start()
            first = await service.query(AgentQueryRequest(query="颐和园地址"))
            run_id = first.orchestration_summary["run_id"]
            gap = store.latest_state_output(run_id, "live_gap_fill") or {}
            promotion = store.latest_state_output(run_id, "knowledge_promote") or {}
            published = promotion.get("results", [{}])[0]
            job_id = published.get("job_id")
            if not job_id:
                raise RuntimeError("closure_missing_publication")
            async with asyncio.timeout(5):
                while resources.jobs.get(job_id)["attempts"] == 0:
                    await asyncio.sleep(0.02)
            resources._stop.set()
            await resources.coordinator
            failed_job = resources.jobs.get(job_id)
        # Simulate a coordinator restart after retry backoff, keeping the real serial Qdrant lane.
        resumed = IndexJobs(repo, resources.jobs.synchronizer,
                            clock=lambda: datetime.now(UTC) + timedelta(seconds=60))
        recovered = await resources.workers.run("dense", resumed.run_pending, limit=10)
        result["sync_recovery"] = float(failed_job["status"] == "pending"
            and failed_job["last_failure_code"] is not None
            and any(j["status"] == "succeeded" for j in recovered))
        envs = [McpEvidenceEnvelope.model_validate(e) for e in gap["mcp_envelopes"]]
        source = envs[0]
        fields = {field.field_path: field.value for field in source.sanitized_fields}
        raw = {"attraction_id": source.attraction_id, "fact_type": "general_description",
            "fact_text": fields["/address"],
            "references": [{"evidence_id": source.call_id, "field_path": "/address",
                            "quote": fields["/address"]}]}
        repeated = PromotionService(repo, PromotionValidator(PromotionPolicy(storage_enabled=True))).promote(
            raw, envs, name="颐和园", run_id=run_id, query_id=first.query_id, trace_id="eval")
        result["promotion_idempotency"] = float(repeated["version_id"] == published["version_id"]
            and repeated["job_id"] == job_id and len(repo.active_versions("summer-palace")) == 1)
        attempts = []
        async def forbidden_tool(*args, **kwargs):
            attempts.append(1)
            raise AssertionError("second query must not call MCP")
        with patch.object(resources.session, "call_tool", forbidden_tool), patch.object(
                SQLiteLexicalRetriever, "retrieve", side_effect=RuntimeError("lexical outage")):
            second = await service.query(AgentQueryRequest(query="颐和园地址"))
        second_id = second.orchestration_summary["run_id"]
        retrieval = store.latest_state_output(second_id, "hybrid_retrieve") or {}
        reports = retrieval.get("retrieval_reports", [])
        hits = [h for r in reports for h in r["final_hits"]]
        result.update(first_tool_calls=gap.get("tool_call_attempt_count", 0),
            promotion_status=published.get("status"), second_tool_calls=len(attempts),
            miss_promote_dense_hit=float(bool(hits) and all(
                h["document_version_id"] == published["version_id"] and h["retrieval_channels"] == ["dense"]
                for h in hits) and second.orchestration_summary["terminal_state"] == "deliver"
                and not any(e.state == "live_gap_fill" for e in store.phase_events(second_id))),
            unsupported_emitted=sum(c.get("status") != "supported"
                for c in second.citation_report.get("decisions", [])))
        result["artifacts"] = {"first_gap": gap, "first_promotion": promotion,
            "second_retrieval": retrieval, "second_citation": second.citation_report,
            "failed_index_job": failed_job, "recovered_index_job": resumed.get(job_id)}
    finally:
        await resources.aclose()
    counters = {"external": 0, "write": 0}
    def forbid(kind):
        def fail(*args, **kwargs):
            counters[kind] += 1
            raise AssertionError("replay forbidden side effect")
        return fail
    before = knowledge_counts(repo)
    with ExitStack() as stack:
        for owner, method, kind in (
            (SingleAttemptLLMClient, "complete", "external"), (BaiduGapTool, "fetch_gap", "external"),
            (BoundedStdioSession, "call_tool", "external"), (PromotionService, "promote", "write"),
            (IndexSynchronizer, "rebuild", "write"), (KnowledgeRepository, "ingest", "write"),
            (KnowledgeRepository, "publish", "write"), (IndexJobs, "run_pending", "write")):
            stack.enter_context(patch.object(owner, method, forbid(kind)))
        replay = await ReplayService(store).replay(query_id=first.query_id)
    result.update(replay_external_calls=counters["external"],
        replay_write_side_effects=counters["write"] + int(knowledge_counts(repo) != before),
        replay_consistent=(replay.response.answer_claims == first.answer_claims
                           and replay.response.citation_report == first.citation_report),
        artifact_refs=["suites/runtime_closure/cases/0/actual/artifacts"])
    return result
