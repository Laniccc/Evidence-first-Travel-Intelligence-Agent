"""Offline-first RAG eval runner with lexical, dense and hybrid ablations."""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from datetime import UTC, datetime, timedelta
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
from app.evidence.claim_decision import evaluate_claims
from app.composition.answer_claim import AnswerClaim
from app.evidence.citation_checker import CitationChecker
from app.evidence.retrieval.contracts import RetrievalPlan, VectorPoint
from app.evidence.retrieval.embedding import DeterministicHashEmbedding, FastEmbedEmbedding
from app.evidence.retrieval.hybrid import HybridRetriever, QdrantDenseRetriever
from app.evidence.retrieval.index_sync import IndexSynchronizer
from app.evidence.retrieval.lexical import SQLiteLexicalRetriever
from app.evidence.retrieval.reranker import filter_and_rerank
from app.evidence.retrieval.report import (
    LatencyBreakdown,
    RetrievalAttempt,
    RetrievalReport,
    RetrievedChunk,
)
from app.evidence.retrieval.fusion import reciprocal_rank_fusion
from app.integrations.qdrant.vector_index import QdrantVectorIndex
from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.replay import ReplayService
from app.orchestration.state_contracts import AgentState, StateContext
from app.orchestration.states.context_loading import ContextLoadingHandler
from app.orchestration.states.ingress import IngressHandler
from app.orchestration.states.llm_understanding import UnderstandingHandler
from app.orchestration.states.retrieval_planning import RetrievalPlanningHandler
from app.orchestration.states.routing import RouteHandler
from app.orchestration.states.evidence_evaluation import EvidenceEvaluationHandler
from app.orchestration.states.hybrid_retrieval import HybridRetrievalHandler
from app.orchestration.states.live_gap_fill import LiveGapFillHandler
from app.orchestration.transition_table import is_allowed_transition
from evals.graders.retrieval import RetrievalCaseResult, grade_retrieval
from evals.graders.state_path import (
    ConversationCaseResult,
    StatePathCaseResult,
    grade_conversations,
    grade_state_paths,
)
from evals.graders.operations import (
    ConsistencyMetrics,
    ConflictCaseResult,
    RecoveryCaseResult,
    grade_conflicts,
    grade_recovery,
)
from evals.graders.evidence import grade_release_gates
from evals.graders.citation import CitationCaseResult, grade_citations
from evals.graders.versioning import VersionCaseResult, grade_versioning


ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / "fixtures" / "knowledge.json"
RETRIEVAL_DATASET = ROOT / "datasets" / "retrieval.jsonl"
VERSIONING_DATASET = ROOT / "datasets" / "versioning.jsonl"
STATE_ROUTING_DATASET = ROOT / "datasets" / "state_routing.jsonl"
EVIDENCE_CONFLICT_DATASET = ROOT / "datasets" / "evidence_conflict.jsonl"
FAILURE_RECOVERY_DATASET = ROOT / "datasets" / "failure_recovery.jsonl"
CITATION_DATASET = ROOT / "datasets" / "citation.jsonl"
MULTI_TURN_DATASET = ROOT / "datasets" / "multi_turn.jsonl"
COMPARISON_DATASET = ROOT / "datasets" / "comparison.jsonl"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=(
            "retrieval",
            "versioning",
            "state_routing",
            "evidence_conflict",
            "failure_recovery",
            "citation",
            "conversation",
            "all",
        ),
        required=True,
    )
    parser.add_argument("--mode", choices=("lexical", "dense", "hybrid"), default="hybrid")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--profile", choices=("offline", "real-embedding"), default="offline")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--fail-on-regression", action="store_true")
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
                # Seed history at its original valid time; production cannot publish expired facts.
                cutoff = datetime.fromisoformat((row.get("valid_from") or fixture["as_of"]).replace("Z", "+00:00"))
                if row.get("valid_to"):
                    cutoff = min(cutoff, datetime.fromisoformat(row["valid_to"].replace("Z", "+00:00")) - timedelta(seconds=1))
                seed_clock = lambda: cutoff
                KnowledgeRepository(repository.db_path, clock=seed_clock).publish(result.version_id)
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
    temp_dir = tempfile.TemporaryDirectory(prefix="rag-eval-", ignore_cleanup_errors=True)
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
        elif mode == "hybrid_no_rerank":
            lexical_hits = lexical.retrieve(plan, limit=20)
            dense_hits = dense.retrieve(plan, limit=20)
            fused = reciprocal_rank_fusion(
                lexical=lexical_hits,
                dense=dense_hits,
            )
            # Keep all production safety filters, but undo the authority/freshness
            # ordering so this arm isolates RRF fusion from deterministic reranking.
            filter_plan = plan.model_copy(update={"top_k": len(fused) or 1})
            filtered, rejections = filter_and_rerank(
                repository,
                plan=filter_plan,
                candidates=fused,
                corpus_version=generation.corpus_version,
            )
            hits = sorted(filtered, key=lambda item: (-item.rrf_score, item.chunk_id))[
                : plan.top_k
            ]
            ranked = [hit.chunk_id for hit in hits]
            reports.append(
                {
                    "case_id": row["case_id"],
                    "ranked_chunk_ids": ranked,
                    "ordering": "rrf_without_authority_freshness_rerank",
                    "post_filter_rejections": [
                        item.model_dump() for item in rejections
                    ],
                }
            )
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
    try:
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
    finally:
        # Fault injection belongs to this suite; do not contaminate healthy-index reuse tests.
        vector_index.delete([key for key, status in corpus["status_by_chunk"].items() if status != "active"],
                            corpus_version=generation.corpus_version, embedding_model=generation.embedding_model)



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


def _operation_plan(*, fact_type: FactType = FactType.OPENING_HOURS) -> RetrievalPlan:
    return RetrievalPlan(
        task_type="fact_query",
        query_text="故宫事实查询",
        attraction_ids=["forbidden-city"],
        fact_types=[fact_type],
        as_of=datetime(2026, 9, 2, tzinfo=UTC),
        top_k=3,
        subtask_id="operation-subtask",
    )


def _operation_chunk(
    *, chunk_id: str, fact_type: str, content: str, authority: float
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_version_id=f"version-{chunk_id}",
        attraction_id="forbidden-city",
        fact_type=fact_type,
        content=content,
        source_id=f"source-{chunk_id}",
        source_url=f"https://example.test/{chunk_id}",
        source_title=chunk_id,
        source_authority=authority,
        content_hash=f"hash-{chunk_id}",
        retrieval_channels=["lexical"],
        rrf_score=0.1,
        final_score=authority,
        corpus_version="eval-corpus",
    )


def _operation_report(
    plan: RetrievalPlan,
    *,
    hits: list[RetrievedChunk] | None = None,
    degradation: str = "none",
    lexical_failure: str | None = None,
    dense_failure: str | None = None,
) -> RetrievalReport:
    hits = hits or []
    return RetrievalReport(
        subtask_id=plan.subtask_id,
        retrieval_plan=plan,
        corpus_version="eval-corpus",
        lexical_attempt=RetrievalAttempt(
            channel="lexical",
            status="failed" if lexical_failure else ("success" if hits else "empty"),
            result_count=0 if lexical_failure else len(hits),
            latency_ms=0,
            failure_code=lexical_failure,
        ),
        dense_attempt=RetrievalAttempt(
            channel="dense",
            status="failed" if dense_failure else ("success" if hits else "empty"),
            result_count=0 if dense_failure else len(hits),
            latency_ms=0,
            failure_code=dense_failure,
        ),
        final_hits=hits,
        degradation=degradation,
        latency_breakdown=LatencyBreakdown(
            lexical_ms=0,
            dense_ms=0,
            fusion_ms=0,
            post_filter_rerank_ms=0,
            total_ms=0,
        ),
    )


def _evidence_conflict_suite() -> dict:
    results = []
    for row in _load_jsonl(EVIDENCE_CONFLICT_DATASET):
        fact_type = FactType(row["fact_type"])
        plan = _operation_plan(fact_type=fact_type)
        hits = [
            _operation_chunk(
                chunk_id=f"{row['case_id']}-{index}",
                fact_type=row["fact_type"],
                content=value,
                authority=row["authorities"][index],
            )
            for index, value in enumerate(row["values"])
        ]
        evaluation = evaluate_claims(
            plans=[plan], reports=[_operation_report(plan, hits=hits)]
        )
        decision = evaluation.claim_decisions[0]
        preferred_index = max(
            range(len(row["authorities"])), key=row["authorities"].__getitem__
        )
        results.append(
            ConflictCaseResult(
                case_id=row["case_id"],
                expected_conflict=row["expected_conflict"],
                actual_conflict=bool(decision.conflict_evidence_ids),
                expected_source_count=len(row["values"]),
                retained_source_count=len(decision.adopted_evidence_ids),
                preferred_authority_ok=decision.adopted_value
                == row["values"][preferred_index],
            )
        )
    return {
        "metrics": grade_conflicts(results).model_dump(),
        "cases": [item.model_dump() for item in results],
    }


class _StaticOperationRetriever:
    def __init__(self, report: RetrievalReport) -> None:
        self.report = report

    async def aretrieve(self, plan: RetrievalPlan) -> RetrievalReport:
        return self.report


class _OperationGapTool:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario

    async def fetch(self, task: dict, *, attempt: int) -> dict:
        if self.scenario == "rate_then_success" and attempt == 1:
            raise RuntimeError("429 rate limit")
        if self.scenario == "malformed_twice":
            return {"unexpected": True}
        return {
            "evidence_id": "live-eval",
            "attraction_id": task["attraction_id"],
            "fact_type": task["fact_type"],
            "content": "故宫今日八点三十分开放",
            "source_name": "故宫官网",
            "source_url": "https://www.dpm.org.cn/visit/hours",
        }


async def _run_recovery_case(row: dict) -> RecoveryCaseResult:
    plan = _operation_plan()
    scenario = row["scenario"]
    hit = _operation_chunk(
        chunk_id="active-hours",
        fact_type="opening_hours",
        content="故宫八点三十分开放",
        authority=1.0,
    )
    context = StateContext(
        run_id=f"eval-{row['case_id']}",
        session_id="eval-session",
        query_id=row["case_id"],
        raw_query="故宫开放时间",
        artifacts={
            AgentState.RETRIEVAL_PLAN.value: {
                "retrieval_plans": [plan.model_dump(mode="json")]
            }
        },
    )
    if scenario in {"dense_timeout", "embedding_error", "both_empty", "all_failed"}:
        report = _operation_report(
            plan,
            hits=[] if scenario in {"both_empty", "all_failed"} else [hit],
            degradation=(
                "lexical_only"
                if scenario in {"dense_timeout", "embedding_error"}
                else ("all_failed" if scenario == "all_failed" else "no_results")
            ),
            lexical_failure="dependency_unavailable" if scenario == "all_failed" else None,
            dense_failure=(
                "timeout"
                if scenario == "dense_timeout"
                else (
                    "embedding_unavailable"
                    if scenario == "embedding_error"
                    else ("dependency_unavailable" if scenario == "all_failed" else None)
                )
            ),
        )
        state_result = await HybridRetrievalHandler(
            retriever=_StaticOperationRetriever(report)
        ).run(context)
        return RecoveryCaseResult(
            case_id=row["case_id"],
            expected_outcome=row["expected_outcome"],
            actual_outcome=state_result.next_state.value,
            attempt_count=0,
            logical_task_count=0,
        )

    empty_report = _operation_report(plan, degradation="no_results")
    context.artifacts[AgentState.HYBRID_RETRIEVE.value] = {
        "retrieval_reports": [empty_report.model_dump(mode="json")]
    }
    context.artifacts[AgentState.EVIDENCE_EVALUATE.value] = {
        "coverage_report": {
            "items": [
                {
                    "claim_type": f"{plan.subtask_id}:opening_hours",
                    "covered": False,
                }
            ]
        }
    }
    gap_result = await LiveGapFillHandler(tool=_OperationGapTool(scenario)).run(context)
    context.artifacts[AgentState.LIVE_GAP_FILL.value] = gap_result.output
    final_evaluation = await EvidenceEvaluationHandler().run(context)
    attempts = gap_result.output["attempts"]
    abstention_correct = (
        final_evaluation.next_state is AgentState.SAFE_FAILURE
        if scenario == "malformed_twice"
        else final_evaluation.next_state is AgentState.COMPOSE
    )
    return RecoveryCaseResult(
        case_id=row["case_id"],
        expected_outcome=row["expected_outcome"],
        actual_outcome=gap_result.next_state.value,
        attempt_count=len(attempts),
        logical_task_count=gap_result.output["logical_gap_task_count"],
        abstention_correct=abstention_correct,
    )


def _failure_recovery_suite() -> dict:
    results = [
        asyncio.run(_run_recovery_case(row))
        for row in _load_jsonl(FAILURE_RECOVERY_DATASET)
    ]
    return {
        "metrics": grade_recovery(results).model_dump(),
        "cases": [item.model_dump() for item in results],
    }


def _citation_suite() -> dict:
    results = []
    audit = []
    for row in _load_jsonl(CITATION_DATASET):
        claim = AnswerClaim(
            claim_id=row["case_id"],
            # Actual fixture fact, not a placeholder label that cannot be grounded.
            text="八点三十分开放",
            claim_type="opening_hours",
            hard_fact=True,
            evidence_ids=row["evidence_ids"],
            conflict_disclosed=row["conflict_disclosed"],
        )
        report = CitationChecker.check(claims=[claim], evidence_index=row["evidence"])
        decision = report.decisions[0]
        actual_supported = decision.status == "supported"
        results.append(
            CitationCaseResult(
                case_id=row["case_id"],
                expected_supported=row["expected_supported"],
                actual_supported=actual_supported,
                expected_abstain=row["expected_abstain"],
                actual_abstain=report.safe_failure,
            )
        )
        audit.append({"case_id": row["case_id"], "decision": decision.model_dump()})
    return {
        "metrics": grade_citations(results).model_dump(),
        "cases": [item.model_dump() for item in results],
        "citation_audit": audit,
    }


async def _understand_and_route(
    row: dict,
    repository: KnowledgeRepository,
    *,
    user_context: dict | None = None,
) -> tuple[StateContext, AgentState]:
    context = StateContext(
        run_id=f"conversation-{row['case_id']}",
        session_id="conversation-session",
        query_id=row["case_id"],
        raw_query=row["query"],
        user_context=user_context or {},
    )
    context_result = await ContextLoadingHandler().run(context)
    context.artifacts[AgentState.CONTEXT.value] = context_result.output
    understanding = await UnderstandingHandler(
        attraction_matcher=repository.find_attractions_in_text
    ).run(context)
    context.artifacts[AgentState.UNDERSTAND.value] = understanding.output
    if understanding.next_state is not AgentState.ROUTE:
        return context, understanding.next_state
    route = await RouteHandler().run(context)
    context.artifacts[AgentState.ROUTE.value] = route.output
    return context, route.next_state


def _conversation_suite(repository: KnowledgeRepository) -> dict:
    results: list[ConversationCaseResult] = []
    for row in _load_jsonl(MULTI_TURN_DATASET):
        context, terminal = asyncio.run(
            _understand_and_route(
                row,
                repository,
                user_context={
                    "conversation_context": {"last_places": [row["previous_place"]]}
                },
            )
        )
        actual_names = context.artifacts.get(AgentState.ROUTE.value, {}).get(
            "attraction_names", []
        )
        results.append(
            ConversationCaseResult(
                case_id=row["case_id"],
                expected_terminal=row["expected_terminal"],
                actual_terminal=terminal.value,
                expected_attractions=[row["expected_attraction"]],
                actual_attractions=actual_names,
            )
        )

    for row in _load_jsonl(COMPARISON_DATASET):
        context, terminal = asyncio.run(_understand_and_route(row, repository))
        route = context.artifacts.get(AgentState.ROUTE.value, {})
        plan_result = asyncio.run(
            RetrievalPlanningHandler(
                attraction_resolver=lambda name: (
                    matches[0].attraction_id
                    if (matches := repository.find_attractions_in_text(name, limit=1))
                    else None
                )
            ).run(context)
        )
        plans = [
            RetrievalPlan.model_validate(item)
            for item in plan_result.output.get("retrieval_plans", [])
        ]
        actual_ids = [plan.attraction_ids[0] for plan in plans]
        fact_sets = [[item.value for item in plan.fact_types] for plan in plans]
        results.append(
            ConversationCaseResult(
                case_id=row["case_id"],
                expected_terminal="comparison",
                actual_terminal=terminal.value,
                expected_attractions=row["expected_attractions"],
                actual_attractions=actual_ids,
                plan_isolation_ok=(
                    route.get("task_type") == "comparison"
                    and len(plans) == 2
                    and len({plan.subtask_id for plan in plans}) == 2
                    and all(items == row["expected_fact_types"] for items in fact_sets)
                ),
            )
        )
    return {
        "metrics": grade_conversations(results).model_dump(),
        "cases": [item.model_dump() for item in results],
    }


async def _replay_is_consistent(store: SQLiteRunStore) -> bool:
    plan = _operation_plan()
    hit = _operation_chunk(
        chunk_id="replay-hours",
        fact_type="opening_hours",
        content="故宫八点三十分开放",
        authority=1.0,
    )
    report = _operation_report(plan, hits=[hit])
    store.start_run(
        run_id="eval-original-run",
        query_id="eval-replay-query",
        session_id="eval-replay-session",
        query="故宫开放时间",
    )
    store.append_phase_event(
        run_id="eval-original-run",
        state=AgentState.RETRIEVAL_PLAN.value,
        status="succeeded",
        attempt=1,
        output={"retrieval_plans": [plan.model_dump(mode="json")]},
    )
    store.append_phase_event(
        run_id="eval-original-run",
        state=AgentState.HYBRID_RETRIEVE.value,
        status="succeeded",
        attempt=1,
        output={"retrieval_reports": [report.model_dump(mode="json")]},
    )
    from app.orchestration.states.delivery import DeliveryHandler
    from app.orchestration.states.answer_composition import GroundedCompositionHandler
    from app.orchestration.states.citation_guard import CitationGuardHandler
    context = StateContext(run_id="eval-original-run", query_id="eval-replay-query",
        session_id="eval-replay-session", raw_query="query",
        artifacts={e.state: e.output for e in store.phase_events("eval-original-run")})
    for state, handler in (("evidence_evaluate", EvidenceEvaluationHandler()), ("compose", GroundedCompositionHandler()),
                           ("citation_guard", CitationGuardHandler())):
        result = await handler.run(context)
        context.artifacts[state] = result.output
    response = await DeliveryHandler().build_response(context)
    store.save_response_snapshot(context, response)
    store.finish_run("eval-original-run", status="succeeded", current_state="deliver")
    replay = await ReplayService(store).replay(query_id="eval-replay-query")
    return bool(
        replay.run.replay_of_run_id == "eval-original-run"
        and replay.response.answer_claims
        and replay.response.answer_claims[0]["evidence_ids"] == ["replay-hours"]
    )


def _consistency_suite(environment) -> dict:
    temp_dir, _, repository, corpus, embedder, vector_index, generation, *_ = environment
    reused = IndexSynchronizer(
        repository,
        vector_index=vector_index,
        embedder=embedder,
    ).rebuild(corpus_version=corpus["fixture"]["corpus_version"])
    active_count = len(repository.list_active_chunks(datetime.now(UTC)))
    index_ok = bool(
        reused.reused
        and reused.generation_id == generation.generation_id
        and reused.indexed_chunk_count == active_count
    )
    store = SQLiteRunStore(Path(temp_dir.name) / "eval-runs.sqlite3")
    replay_ok = asyncio.run(_replay_is_consistent(store))
    return ConsistencyMetrics(
        index_rebuild_consistency=float(index_ok),
        replay_consistency=float(replay_ok),
    ).model_dump()


def _corpus_summary(corpus: dict, generation) -> dict:
    return {
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
    }


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if payload.get("suite") != "all":
        return
    lines = [
        "# Final offline evaluation",
        "",
        f"- Result: **{'PASS' if payload['gates']['passed'] else 'FAIL'}**",
        f"- Cases: {payload['case_count']}",
        f"- Corpus: `{payload['corpus']['corpus_version']}`",
        "- Limitation: deterministic feature hashing validates control flow and ranking mechanics, not real semantic embedding quality.",
        "",
        "## Release gates",
        "",
        "| Metric | Actual | Gate | Result |",
        "|---|---:|---:|---|",
    ]
    lines.extend(
        f"| {item['metric']} | {item['actual']:.4f} | {item['operator']} {item['threshold']:.2f} | {'PASS' if item['passed'] else 'FAIL'} |"
        for item in payload["gates"]["checks"]
    )
    lines.extend(
        [
            "",
            "## Retrieval ablations",
            "",
            "| Mode | Recall@3 | MRR | nDCG@5 | Metadata | Provenance |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, result in payload["ablations"].items():
        metrics = result["metrics"]
        lines.append(
            f"| {name} | {metrics['recall_at_3']:.4f} | {metrics['mrr']:.4f} | "
            f"{metrics['ndcg_at_5']:.4f} | {metrics['metadata_filter_accuracy']:.4f} | "
            f"{metrics['provenance_completeness']:.4f} |"
        )
    lines.extend(
        [
            "",
            "`hybrid` applies RRF plus mandatory version/hash filters; "
            "`hybrid+rerank` additionally orders by authority and freshness. "
            "Equal scores on this controlled corpus are not evidence of semantic lift.",
        ]
    )
    lines.extend(["", "## Bad cases", ""])
    lines.append("None in this deterministic regression set." if not payload["bad_cases"] else "\n".join(f"- {item}" for item in payload["bad_cases"]))
    path.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _all_suite(environment) -> dict:
    _, _, repository, corpus, _, _, generation, *_ = environment
    ablations = {
        "lexical-only": _retrieval_suite("lexical", environment),
        "dense-only": _retrieval_suite("dense", environment),
        "hybrid": _retrieval_suite("hybrid_no_rerank", environment),
        "hybrid+rerank": _retrieval_suite("hybrid", environment),
    }
    suites = {
        "versioning": _versioning_suite(environment),
        "state_routing": _state_routing_suite(),
        "evidence_conflict": _evidence_conflict_suite(),
        "failure_recovery": _failure_recovery_suite(),
        "citation": _citation_suite(),
        "conversation": _conversation_suite(repository),
    }
    consistency = _consistency_suite(environment)
    retrieval = ablations["hybrid+rerank"]["metrics"]
    versioning = suites["versioning"]["metrics"]
    routing = suites["state_routing"]["metrics"]
    citation = suites["citation"]["metrics"]
    gate_metrics = {
        "recall_at_3": retrieval["recall_at_3"],
        "mrr": retrieval["mrr"],
        "ndcg_at_5": retrieval["ndcg_at_5"],
        "metadata_filter_accuracy": retrieval["metadata_filter_accuracy"],
        "non_active_leakage_rate": versioning["non_active_leakage_rate"],
        "state_path_accuracy": routing["path_accuracy"],
        "illegal_transitions": routing["illegal_transitions"],
        "stale_vector_rejection": versioning["stale_vector_rejection"],
        "index_rebuild_consistency": consistency["index_rebuild_consistency"],
        "unsupported_hard_facts": citation["unsupported_hard_facts"],
        "citation_precision": citation["citation_precision"],
        "abstention_precision": citation["abstention_precision"],
        "replay_consistency": consistency["replay_consistency"],
    }
    gates = grade_release_gates(gate_metrics).model_dump()
    case_count = (
        len(_load_jsonl(RETRIEVAL_DATASET))
        + sum(len(value["cases"]) for value in suites.values())
    )
    return {
        "suite": "all",
        "profile": "offline",
        "case_count": case_count,
        "offline_embedding_limitation": (
            "Deterministic feature hashing validates orchestration, filters, fusion and version controls; "
            "it is not evidence of real semantic embedding quality."
        ),
        "corpus": _corpus_summary(corpus, generation),
        "ablations": ablations,
        "suites": suites,
        "consistency": consistency,
        "gate_metrics": gate_metrics,
        "gates": gates,
        "bad_cases": gates["failures"],
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.offline and args.profile == "real-embedding":
        raise SystemExit("--offline cannot be combined with --profile real-embedding")
    profile = "offline" if args.offline else args.profile
    if args.suite in {"all", "conversation"}:
        environment = _environment(profile=profile)
        temp_dir, client, repository, corpus, _, _, generation, *_ = environment
        try:
            if args.suite == "all":
                payload = _all_suite(environment)
            else:
                payload = {
                    "suite": "conversation",
                    "mode": "deterministic",
                    "profile": profile,
                    "corpus": _corpus_summary(corpus, generation),
                    **_conversation_suite(repository),
                }
            _write_report(args.report, payload)
            metrics = payload.get("gate_metrics") or payload.get("metrics") or {}
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            if args.fail_on_regression and not payload.get("gates", {}).get("passed", True):
                return 1
            return 0
        finally:
            client.close()
            temp_dir.cleanup()
    if args.suite in {
        "state_routing",
        "evidence_conflict",
        "failure_recovery",
        "citation",
    }:
        suite_result = (
            _state_routing_suite()
            if args.suite == "state_routing"
            else (
                _evidence_conflict_suite()
                if args.suite == "evidence_conflict"
                else (
                    _failure_recovery_suite()
                    if args.suite == "failure_recovery"
                    else _citation_suite()
                )
            )
        )
        payload = {
            "suite": args.suite,
            "mode": "deterministic",
            "profile": "offline",
            **suite_result,
        }
        _write_report(args.report, payload)
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
            "corpus": _corpus_summary(corpus, generation),
            **suite_result,
        }
        _write_report(args.report, payload)
        print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    finally:
        client.close()
        temp_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
