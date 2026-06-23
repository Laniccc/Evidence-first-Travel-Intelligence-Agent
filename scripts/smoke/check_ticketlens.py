#!/usr/bin/env python3
"""Manual smoke: TicketLens REST provider."""

from __future__ import annotations

import argparse
import asyncio

from _bootstrap import AGENT  # noqa: F401 — side effect: sys.path

from app.config import get_settings
from tools.ticketing.ticketlens_tool import TicketLensExperienceTool


def _summarize_evidence(evidence: list) -> str:
    if not evidence:
        return "(no evidence)"
    ev = evidence[0]
    parts = [f"{c.claim_type.value}={c.value}" for c in ev.claims[:3]]
    return f"{ev.source_name}: " + "; ".join(parts)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default=None)
    parser.add_argument("--country", default="China")
    args = parser.parse_args()

    settings = get_settings()
    tool = TicketLensExperienceTool(settings)
    print(f"enabled={settings.ticketlens_enabled}")
    print(f"configured={tool.is_configured()}")

    evidence = await tool.run(place_name=args.place, city=args.city, country=args.country)
    meta = tool.last_run_meta
    print(f"success={not meta.get('error')}")
    print(f"count={len(evidence)}")
    print(f"summary={_summarize_evidence(evidence)}")
    if meta.get("error"):
        print(f"error={meta['error']}")
    if meta.get("snapshot_saved_count") is not None:
        print(f"snapshot_saved_count={meta['snapshot_saved_count']}")
    return 0 if evidence or meta.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
