"""Command-line maintenance surface for the attraction knowledge corpus."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from qdrant_client import QdrantClient

from app.evidence.knowledge.models import (
    Attraction,
    FactChunkDraft,
    FactType,
    KnowledgeDocument,
    SourceType,
)
from app.evidence.knowledge.index_jobs import IndexJobs
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.knowledge.service import KnowledgeLifecycleService
from app.evidence.retrieval.embedding import DeterministicHashEmbedding, FastEmbedEmbedding
from app.evidence.retrieval.index_sync import IndexSynchronizer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed", help="ingest fixture documents")
    seed.add_argument("--db", required=True, type=Path)
    seed.add_argument("--fixture", required=True, type=Path)
    seed.add_argument("--auto-publish", action="store_true")

    refresh = subparsers.add_parser("refresh", help="re-ingest a source fixture")
    refresh.add_argument("--db", required=True, type=Path)
    refresh.add_argument("--source-id", required=True)
    refresh.add_argument("--fixture", required=True, type=Path)

    publish = subparsers.add_parser("publish", help="publish one pending version")
    publish.add_argument("--db", required=True, type=Path)
    publish.add_argument("--version-id", required=True)

    inspect = subparsers.add_parser("inspect", help="inspect attraction versions or vector index")
    inspect.add_argument("--db", required=True, type=Path)
    inspect.add_argument("--attraction")
    inspect.add_argument("--index", action="store_true")

    reindex = subparsers.add_parser("reindex", help="rebuild the Qdrant vector generation")
    sync_pending = subparsers.add_parser("sync-pending", help="resume bounded durable index jobs")
    sync_pending.add_argument("--limit", type=int, default=10)
    for target in (reindex, sync_pending):
        target.add_argument("--db", required=True, type=Path)
        target.add_argument("--qdrant-mode", choices=("local", "server"), default="local")
        target.add_argument("--qdrant-path", type=Path)
        target.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
        target.add_argument("--qdrant-api-key")
        target.add_argument("--collection", default="attraction-facts")
        target.add_argument("--embedding-mode", choices=("deterministic", "fastembed"), default="deterministic")
        target.add_argument("--embedding-model", default="BAAI/bge-small-zh-v1.5")
        target.add_argument("--dimension", type=int, default=512)
        target.add_argument("--corpus-version")
    return parser


def _load_documents(path: Path) -> list[KnowledgeDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "documents" in payload:
        rows = payload["documents"]
    elif isinstance(payload, dict) and "active_documents" in payload:
        # The checked-in Eval corpus is also the smallest runnable demo corpus.
        # Historical/conflict/rejected rows are seeded only by the Eval runner,
        # while the maintenance CLI starts a clean runtime from active facts.
        rows = payload["active_documents"]
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = [payload]
    return [_document_from_row(row) for row in rows]


def _document_from_row(row: dict) -> KnowledgeDocument:
    if "attraction" in row and "chunks" in row:
        return KnowledgeDocument.model_validate(row)
    facts = row.get("facts")
    if not isinstance(facts, list):
        return KnowledgeDocument.model_validate(row)
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
                chunk_id=fact.get("chunk_id"),
                fact_type=FactType(fact["fact_type"]),
                content=fact["content"],
                locator=fact.get("locator"),
            )
            for fact in facts
        ],
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = KnowledgeRepository(args.db)
    service = KnowledgeLifecycleService(repository)

    if args.command == "seed":
        results = [
            service.ingest(document, auto_publish=args.auto_publish).model_dump(mode="json")
            for document in _load_documents(args.fixture)
        ]
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if args.command == "refresh":
        document = next(
            (
                item
                for item in _load_documents(args.fixture)
                if item.source_id == args.source_id
            ),
            None,
        )
        if document is None:
            raise SystemExit(f"source_id not found in fixture: {args.source_id}")
        print(service.ingest(document).model_dump_json(indent=2))
        return 0
    if args.command == "publish":
        print(repository.publish(args.version_id).model_dump_json(indent=2))
        return 0
    if args.command == "inspect":
        if not args.attraction and not args.index:
            raise SystemExit("inspect requires --attraction and/or --index")
        payload = {}
        if args.attraction:
            payload["knowledge"] = repository.inspect_attraction(args.attraction)
        if args.index:
            generation = repository.active_index_generation()
            payload["index"] = generation.model_dump(mode="json") if generation else None
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command in {"reindex", "sync-pending"}:
        # This CLI module is the delivery/composition boundary. The concrete adapter
        # stays out of the evidence domain's static dependency graph.
        vector_index_class = importlib.import_module(
            "app.integrations.qdrant.vector_index"
        ).QdrantVectorIndex
        if args.qdrant_mode == "local":
            path = args.qdrant_path or args.db.parent / "qdrant"
            client = QdrantClient(path=str(path))
        else:
            client = QdrantClient(
                url=args.qdrant_url,
                api_key=args.qdrant_api_key or None,
            )
        embedder = (
            DeterministicHashEmbedding(dimension=args.dimension)
            if args.embedding_mode == "deterministic"
            else FastEmbedEmbedding(args.embedding_model, args.dimension)
        )
        index = vector_index_class(
            client,
            collection=args.collection,
            dimension=args.dimension,
        )
        try:
            synchronizer = IndexSynchronizer(
                repository,
                vector_index=index,
                embedder=embedder,
            )
            if args.command == "sync-pending":
                results = IndexJobs(repository, synchronizer).run_pending(limit=args.limit)
                print(json.dumps(results, ensure_ascii=False, indent=2))
                with repository._connect() as db:
                    unfinished = db.execute("SELECT count(*) FROM index_sync_job WHERE status<>\'succeeded\'").fetchone()[0]
                return 1 if unfinished else 0
            result = synchronizer.rebuild(corpus_version=args.corpus_version or repository.compute_corpus_version())
            print(result.model_dump_json(indent=2))
        finally:
            client.close()
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
