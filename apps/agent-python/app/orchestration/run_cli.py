"""CLI for inspecting and replaying persisted Agent runs."""

from __future__ import annotations

import argparse
import asyncio

from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.replay import ReplayService
from app.orchestration.run_inspector import RunInspector


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or replay an Agent run")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--db", required=True)
    inspect_parser.add_argument("--query-id", required=True)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("--db", required=True)
    replay_parser.add_argument("--query-id", required=True)
    replay_parser.add_argument("--from-state", default="evidence_evaluate")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    store = SQLiteRunStore(args.db)
    if args.command == "inspect":
        payload = RunInspector(store).inspect(args.query_id)
    else:
        payload = asyncio.run(
            ReplayService(store).replay(
                query_id=args.query_id, from_state=args.from_state
            )
        )
    print(payload.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
