"""Command-line maintenance surface for the attraction knowledge corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evidence.knowledge.models import KnowledgeDocument
from app.evidence.knowledge.repository import KnowledgeRepository
from app.evidence.knowledge.service import KnowledgeLifecycleService


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

    inspect = subparsers.add_parser("inspect", help="inspect attraction versions")
    inspect.add_argument("--db", required=True, type=Path)
    inspect.add_argument("--attraction", required=True)
    return parser


def _load_documents(path: Path) -> list[KnowledgeDocument]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("documents", payload) if isinstance(payload, dict) else payload
    return [KnowledgeDocument.model_validate(row) for row in rows]


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
        print(json.dumps(repository.inspect_attraction(args.attraction), ensure_ascii=False, indent=2))
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
