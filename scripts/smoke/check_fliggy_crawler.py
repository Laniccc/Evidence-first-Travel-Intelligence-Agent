#!/usr/bin/env python3
"""Manual smoke: Fliggy ticket snapshot (FlyAI API or subprocess crawler)."""

from __future__ import annotations

import argparse
import asyncio

import _bootstrap  # noqa: F401 — sys.path

from app.config import get_settings

_fliggy_mod = _bootstrap.import_tools_module("crawlers.fliggy_crawler_tool")
FliggyTicketSnapshotCrawlerTool = _fliggy_mod.FliggyTicketSnapshotCrawlerTool
_provider_config = _bootstrap.import_tools_module("ticketing.provider_config")
fliggy_flyai_configured = _provider_config.fliggy_flyai_configured


def _summarize(evidence: list) -> str:
    if not evidence:
        return "(no evidence)"
    ev = evidence[0]
    return "; ".join(f"{c.claim_type.value}={str(c.value)[:60]}" for c in ev.claims[:3])


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default=None)
    parser.add_argument("--country", default="China")
    args = parser.parse_args()

    settings = get_settings()
    tool = FliggyTicketSnapshotCrawlerTool(settings)
    print(f"enabled={settings.fliggy_ticket_crawler_enabled and settings.enable_ticket_crawler_providers}")
    print(f"flyai={fliggy_flyai_configured(settings)}")
    print(f"configured={tool.is_configured()}")
    print(f"command={tool.command or '(empty)'}")

    evidence = await tool.run(
        place_name=args.place,
        city=args.city,
        country=args.country,
        query=args.place,
        claim_type="ticket_price_candidate",
    )
    meta = tool.last_run_meta
    print(f"transport={meta.get('transport', 'unknown')}")
    print(f"success={meta.get('error') is None}")
    print(f"output_parse_status={meta.get('output_parse_status')}")
    print(f"count={len(evidence)}")
    print(f"summary={_summarize(evidence)}")
    if meta.get("snapshot_saved_count") is not None:
        print(f"snapshot_saved_count={meta['snapshot_saved_count']}")
    if meta.get("error"):
        print(f"error={meta['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
