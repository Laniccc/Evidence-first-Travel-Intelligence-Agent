"""Offline-first RAG eval runner with lexical, dense and hybrid ablations."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

from qdrant_client import QdrantClient

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.retrieval.contracts import RetrievalPlan, VectorPoint
from app.evidence.retrieval.embedding import DeterministicHashEmbedding, FastEmbedEmbedding
from app.evidence.retrieval.hybrid import HybridRetriever, QdrantDenseRetriever
from app.evidence.retrieval.index_sync import IndexSynchronizer
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.evidence.retrieval.reranker import filter_and_rerank
from app.evidence.retrieval.fusion import reciprocal_rank_fusion
from app.integrations.qdrant.vector_index import QdrantVectorIndex
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.context_loading import ContextLoadingHandler
from app.orchestration.states.ingress import IngressHandler
from app.orchestration.states.llm_understanding import UnderstandingHandler
from app.orchestration.states.routing import RouteHandler
from app.orchestration.transition_table import is_allowed_transition
from evals.graders.retrieval import RetrievalCaseResult, grade_retrieval
from evals.graders.state_path import StatePathCaseResult, grade_state_paths
from evals.graders.versioning import VersionCaseResult, grade_versioning


ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / "fixtures" / "knowledge.json"
RETRIEVAL_DATASET = ROOT / "datasets" / "retrieval.jsonl"
VERSIONING_DATASET = ROOT / "datasets" / "versioning.jsonl"
STATE_ROUTING_DATASET = ROOT / "datasets" / "state_routing.jsonl"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", choices=("retrieval", "versioning", "state_routing"), required=True
    )
    parser.add_argument("--mode", choices=("lexical", "dense", "hybrid"), default="hybrid")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--profile", choices=("offline", "real-embedding"), default="offline")
    parser.add_argument("--report", required=True, type=Path)
    return parser


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _document(row: dict) -> KnowledgeDocument:
    facts = row["facts"]
    return KnowledgeDocument(
        source_id=row["source_id"],
        attraction=Attraction(
            attraction_id=row["attraction_id"],
            name=row["name"],
            aliases=row.get("aliases", []),
            city=row.get("city"),
            country=row.get("country"),
        ),
        url=row["url"],
        title=row["title"],
        source_type=SourceType(row["source_type"]),
        content="\n".join(fact["content"] for fact in facts),
        valid_from=row.get("valid_from"),
        valid_to=row.get("valid_to"),
        chunks=[
            FactChunkDraft(
                chunk_id=fact["chunk_id"],
                fact_type=FactType(fact["fact_type"]),
                content=fact["content"],
                locator=fact.get("locator"),
            )
            for fact in facts
        ],
    )


def _seed(repository: KnowledgeRepository) -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    status_by_chunk = {}
    sections = ("historical_documents", "active_documents", "conflict_documents", "review_documents")
    for section in sections:
        for row in fixture[section]:
            result = repository.ingest(_document(row))
            status = row["expected_status"]
            if status in {"superseded", "expired", "active"}:
                repository.publish(result.version_id)
            elif status == "rejected":
                repository.reject(result.version_id, reason="eval fixture rejected")
            for fact in row["facts"]:
                status_by_chunk[fact["chunk_id"]] = status
    repository.expire_due(datetime.fromisoformat(fixture["as_of"].replace("Z", "+00:00")))
    active_chunks = repository.list_active_chunks(
        datetime.fromisoformat(fixture["as_of"].replace("Z", "+00:00"))
    )
    actual_statuses = {
        chunk_id: repository.get_chunk(chunk_id).version_status.value
        for chunk_id in status_by_chunk
    }
    expected_statuses = dict(status_by_chunk)
    for chunk_id, status in list(expected_statuses.items()):
        if status == "superseded":
            expected_statuses[chunk_id] = "superseded"
    if actual_statuses != expected_statuses:
        mismatches = {
            chunk_id: {"expected": expected_statuses[chunk_id], "actual": actual_statuses[chunk_id]}
            for chunk_id in expected_statuses
            if expected_statuses[chunk_id] != actual_statuses[chunk_id]
        }
        raise RuntimeError(f"fixture lifecycle mismatch: {mismatches}")
    return {
        "fixture": fixture,
        "status_by_chunk": status_by_chunk,
        "active_chunk_count": len(active_chunks),
        "attraction_count": len({chunk.attraction_id for chunk in active_chunks}),
        "conflict_group_count": sum(
            1
            for row in fixture["conflict_documents"]
            for fact in row["facts"]
            if fact.get("conflict_group")
        ),
    }


def _environment(*, profile: str):
    temp_dir = tempfile.TemporaryDirectory(prefix="rag-eval-")
    repository = KnowledgeRepository(Path(temp_dir.name) / "knowledge.sqlite3")
    corpus = _seed(repository)
    dimension = 256 if profile == "offline" else 512
    embedder = (
        DeterministicHashEmbedding(dimension=dimension)
        if profile == "offline"
        else FastEmbedEmbedding("BAAI/bge-small-zh-v1.5", dimension=dimension)
    )
    client = QdrantClient(":memory:")
    vector_index = QdrantVectorIndex(client, collection="rag-eval", dimension=dimension)
    generation = IndexSynchronizer(
        repository,
        vector_index=vector_index,
        embedder=embedder,
    ).rebuild(corpus_version=corpus["fixture"]["corpus_version"])
    lexical = SQLiteLexicalRetriever(repository)
    dense = QdrantDenseRetriever(repository, vector_index=vector_index, embedder=embedder)
    hybrid = HybridRetriever(repository=repository, lexical=lexical, dense=dense)
    return temp_dir, client, repository, corpus, embedder, vector_index, generation, lexical, dense, hybrid


def _plan(row: dict, *, as_of: str, subtask_id: str | None = None) -> RetrievalPlan:
    attraction_ids = row["attraction_ids"] if "attraction_ids" in row else [row["attraction_id"]]
    fact_types = row["fact_types"] if "fact_types" in row else [row["fact_type"]]
    return RetrievalPlan(
        task_type=row.get("task_type", "fact_query"),
        query_text=row["query_text"],
        attraction_ids=attraction_ids,
        fact_types=[FactType(item) for item in fact_types],
        as_of=datetime.fromisoformat(as_of.replace("Z", "+00:00")),
        top_k=5,
        subtask_id=subtask_id or row["case_id"],
    )


def _retrieval_suite(mode: str, environment) -> dict:
    _, _, repository, corpus, _, _, generation, lexical, dense, hybrid = environment
    rows = _load_jsonl(RETRIEVAL_DATASET)
    case_results = []
    reports = []
    for row in rows:
        plan = _plan(row, as_of=corpus["fixture"]["as_of"])
        if mode == "hybrid":
            report = hybrid.retrieve(plan)
            ranked = [hit.chunk_id for hit in report.final_hits]
            hits = report.final_hits
            reports.append(report.model_dump(mode="json"))
        else:
            channel_hits = (lexical if mode == "lexical" else dense).retrieve(plan, limit=20)
            fused = reciprocal_rank_fusion(
                lexical=channel_hits if mode == "lexical" else [],
                dense=channel_hits if mode == "dense" else [],
            )
            hits, rejections = filter_and_rerank(
                repository,
                plan=plan,
                candidates=fused,
                corpus_version=generation.corpus_version,
            )
            ranked = [hit.chunk_id for hit in hits]
            reports.append(
                {
                    "case_id": row["case_id"],
                    "ranked_chunk_ids": ranked,
                    "post_filter_rejections": [item.model_dump() for item in rejections],
                }
            )
        metadata_ok = all(
            hit.attraction_id in plan.attraction_ids
            and (not plan.fact_types or hit.fact_type in {item.value for item in plan.fact_types})
            for hit in hits
        )
        provenance_complete = all(
            hit.source_id and hit.source_url and hit.content_hash and hit.document_version_id
            for hit in hits
        )
        case_results.append(
            RetrievalCaseResult(
                case_id=row["case_id"],
                expected_chunk_ids=row["expected_chunk_ids"],
                ranked_chunk_ids=ranked,
                metadata_filter_ok=metadata_ok,
                provenance_complete=provenance_complete,
            )
        )
    return {
        "metrics": grade_retrieval(case_results).model_dump(),
        "cases": [item.model_dump() for item in case_results],
        "retrieval_reports": reports,
    }


def _inject_non_active_points(repository, corpus, embedder, vector_index, generation) -> None:
    points = []
    for chunk_id, status in corpus["status_by_chunk"].items():
        if status == "active":
            continue
        chunk = repository.get_chunk(chunk_id)
        points.append(
            VectorPoint(
                chunk_id=chunk.chunk_id,
                vector=embedder.embed_query(chunk.content),
                attraction_id=chunk.attraction_id,
                fact_type=chunk.fact_type.value,
                document_version_id=chunk.document_version_id,
                content_hash=chunk.content_hash,
                corpus_version=generation.corpus_version,
                embedding_model=generation.embedding_model,
                source_id=chunk.source_id,
                source_authority=chunk.source_authority,
                valid_from=chunk.valid_from,
                valid_to=chunk.valid_to,
            )
        )
    vector_index.upsert(points)


def _versioning_suite(environment) -> dict:
    _, _, repository, corpus, embedder, vector_index, generation, lexical, dense, _ = environment
    _inject_non_active_points(repository, corpus, embedder, vector_index, generation)
    rows = _load_jsonl(VERSIONING_DATASET)
    results = []
    rejection_audit = []
    for row in rows:
        plan = _plan(row, as_of=corpus["fixture"]["as_of"])
        report = HybridRetriever(repository=repository, lexical=lexical, dense=dense).retrieve(plan)
        ranked = [hit.chunk_id for hit in report.final_hits]
        rejections = [
            item.model_dump()
            for item in report.post_filter_rejections
            if item.chunk_id == row["chunk_id"]
        ]
        results.append(
            VersionCaseResult(
                case_id=row["case_id"],
                status=row["status"],
                returned=row["chunk_id"] in ranked,
                rejected_by_post_filter=bool(rejections),
            )
        )
        rejection_audit.append(
            {"case_id": row["case_id"], "target_chunk_id": row["chunk_id"], "rejections": rejections}
        )
    return {
        "metrics": grade_versioning(results).model_dump(),
        "cases": [item.model_dump() for item in results],
        "rejection_audit": rejection_audit,
    }


async def _run_routing_case(row: dict, repository: KnowledgeRepository) -> StatePathCaseResult:
    context = StateContext(
        run_id=f"eval-{row['case_id']}",
        session_id=f"session-{row['case_id']}",
        query_id=row["case_id"],
        raw_query=row["query"],
    )
    path = [AgentState.INGRESS]
    handlers = {
        AgentState.INGRESS: IngressHandler(),
        AgentState.CONTEXT: ContextLoadingHandler(),
        AgentState.UNDERSTAND: UnderstandingHandler(
            attraction_matcher=repository.find_attractions_in_text
        ),
        AgentState.ROUTE: RouteHandler(),
    }
    state = AgentState.INGRESS
    illegal = 0
    while state in handlers:
        result = await handlers[state].run(context)
        context.artifacts[state.value] = result.output
        if not is_allowed_transition(state, result.next_state):
            illegal += 1
            break
        state = result.next_state
        path.append(state)
    return StatePathCaseResult(
        case_id=row["case_id"],
        expected_terminal=row["expected_terminal"],
        actual_terminal=state.value,
        illegal_transition_count=illegal,
    )


def _state_routing_suite() -> dict:
    rows = _load_jsonl(STATE_ROUTING_DATASET)
    with tempfile.TemporaryDirectory(prefix="routing-eval-") as temp_dir:
        repository = KnowledgeRepository(Path(temp_dir) / "knowledge.sqlite3")
        _seed(repository)
        results = [asyncio.run(_run_routing_case(row, repository)) for row in rows]
        return {
            "metrics": grade_state_paths(results).model_dump(),
            "cases": [item.model_dump() for item in results],
        }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.offline and args.profile == "real-embedding":
        raise SystemExit("--offline cannot be combined with --profile real-embedding")
    profile = "offline" if args.offline else args.profile
    if args.suite == "state_routing":
        payload = {
            "suite": args.suite,
            "mode": "deterministic",
            "profile": "offline",
            **_state_routing_suite(),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
        return 0
    environment = _environment(profile=profile)
    temp_dir, client, _, corpus, _, _, generation, _, _, _ = environment
    try:
        suite_result = (
            _retrieval_suite(args.mode, environment)
            if args.suite == "retrieval"
            else _versioning_suite(environment)
        )
        payload = {
            "suite": args.suite,
            "mode": args.mode,
            "profile": profile,
            "offline_embedding_limitation": (
                "Deterministic feature hashing validates orchestration and ranking mechanics; "
                "it is not evidence of real semantic embedding quality."
                if profile == "offline"
                else None
            ),
            "corpus": {
                "corpus_version": generation.corpus_version,
                "embedding_model": generation.embedding_model,
                "attraction_count": corpus["attraction_count"],
                "active_chunk_count": corpus["active_chunk_count"],
                "superseded_or_expired_count": sum(
                    status in {"superseded", "expired"}
                    for status in corpus["status_by_chunk"].values()
                ),
                "pending_or_rejected_count": sum(
                    status in {"pending", "rejected"}
                    for status in corpus["status_by_chunk"].values()
                ),
                "conflict_group_count": corpus["conflict_group_count"],
            },
            **suite_result,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    finally:
        client.close()
        temp_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
