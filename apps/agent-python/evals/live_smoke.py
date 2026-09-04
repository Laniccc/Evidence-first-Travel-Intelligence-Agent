"""Opt-in bounded real-provider smoke. Exit 2 means not run/blocked, never success."""
import argparse
import asyncio
from contextlib import redirect_stdout, redirect_stderr
import json
import logging
import os
from pathlib import Path
import tempfile

from app.config import Settings
from evals.metadata import runtime_metadata


def load_settings():
    return Settings()


class BoundedCall:
    def __init__(self, target, *, limit):
        self.target, self.limit, self.count = target, limit, 0

    async def __call__(self, *args, **kwargs):
        if self.count >= self.limit:
            raise RuntimeError("smoke_call_budget_exhausted")
        self.count += 1
        return await self.target(*args, **kwargs)


async def run_smoke(settings, args, report):
    from app.main import build_runtime
    from app.contracts.request import AgentQueryRequest
    from app.evidence.knowledge.models import Attraction, KnowledgeDocument, FactChunkDraft
    from app.evidence.knowledge.repository import KnowledgeRepository
    from app.orchestration.agent_core_store import SQLiteRunStore
    with tempfile.TemporaryDirectory(prefix="travel-live-smoke-") as folder:
        directory = Path(folder)
        # Isolated data stores: never ingest into or rebuild the user's actual database.
        config = settings.model_copy(update={"agent_runtime_profile": "online", "debug": False,
            "bounded_baidu_enabled": True, "knowledge_promotion_enabled": True, "baidu_storage_permitted": True,
            "knowledge_db_path": str(directory / "k.db"), "agent_run_db_path": str(directory / "r.db"),
            "qdrant_mode": "local", "qdrant_local_path": str(directory / "qdrant"),
            "embedding_mode": "deterministic", "embedding_dimension": 32, "index_job_poll_seconds": 0.05})
        repo = KnowledgeRepository(config.knowledge_db_path)
        repo.ingest(KnowledgeDocument(source_id="smoke-catalog", attraction=Attraction(
            attraction_id="summer-palace", name="颐和园", city="北京市"),
            url="https://example.invalid/catalog-only", title="catalog-only", source_type="structured",
            content="catalog-only", chunks=[FactChunkDraft(fact_type="visitor_notice", content="catalog-only")]))
        service, _, resources = build_runtime(config)
        if resources.model is None or resources.session is None:
            await resources.aclose()
            report.update(status="blocked", reason="provider_runtime_unavailable")
            return
        llm = BoundedCall(resources.model.complete, limit=args.max_llm_calls)
        tools = BoundedCall(resources.session.call_tool, limit=args.max_tool_calls)
        resources.model.complete, resources.session.call_tool = llm, tools
        try:
            async with asyncio.timeout(60):
                await resources.start()
                response = await service.query(AgentQueryRequest(query="颐和园的地址是什么？"))
                store = SQLiteRunStore(config.agent_run_db_path)
                run_id = response.orchestration_summary["run_id"]
                outputs = {e.state: e.output for e in store.phase_events(run_id)}
                gap = outputs.get("live_gap_fill", {})
                promotion = outputs.get("knowledge_promote", {})
                jobs = [r["job_id"] for r in promotion.get("results", []) if r.get("job_id")]
                async with asyncio.timeout(5):
                    while jobs and any(resources.jobs.get(j)["status"] in {"pending", "running"} for j in jobs):
                        await asyncio.sleep(0.05)
                checks = {
                    "model_understanding": outputs.get("understand", {}).get("understanding_path") in {"model", "repair"},
                    "mcp_evidence_present": bool(gap.get("mcp_envelopes")),
                    "active_publication": any(r.get("status") == "active" for r in promotion.get("results", [])),
                    "index_synchronized": bool(jobs) and all(resources.jobs.get(j)["status"] == "succeeded" for j in jobs),
                    "guarded_answer": bool(response.answer_claims) and bool((response.citation_report or {}).get("passed")),
                    "delivered": response.orchestration_summary["terminal_state"] == "deliver",
                }
                report.update(status="passed" if all(checks.values()) else "failed",
                              reason=None if all(checks.values()) else "acceptance_checks_failed", checks=checks)
        except Exception:
            # No exception text, prompts, POI payloads, addresses, keys or URL query strings.
            report.update(status="failed", reason="smoke_execution_failed")
        finally:
            report.update(llm_calls=llm.count, tool_calls=tools.count)
            await resources.aclose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--allow-data-retention", action="store_true")
    parser.add_argument("--max-tool-calls", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--max-llm-calls", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    report = {"status": "not_run", "reason": "live_consent_required", "llm_calls": 0, "tool_calls": 0,
        "checks": {}, "profile": "live-providers-deterministic-index",
        "metadata": runtime_metadata(embedding_model="deterministic-hash-v1"),
        "retention": "temporary_databases_deleted; report_contains_only_metadata_counts_and_checks"}
    if args.allow_live and not args.allow_data_retention:
        report["reason"] = "data_retention_consent_required"
    elif args.allow_live and args.allow_data_retention:
        settings = load_settings()
        if not settings.llm_api_key() or not settings.baidu_map_ak:
            report.update(status="blocked", reason="credentials_missing")
        else:
            report["metadata"]["llm_model"] = settings.llm_model()
            # Runtime logs are not part of the retained smoke report.
            previous = logging.root.manager.disable
            with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
                logging.disable(logging.CRITICAL)
                try:
                    asyncio.run(run_smoke(settings, args, report))
                except Exception:
                    report.update(status="failed", reason="smoke_setup_or_cleanup_failed")
                finally:
                    logging.disable(previous)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "reason": report["reason"]}))
    return 0 if report["status"] == "passed" else 2 if report["status"] in {"not_run", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
