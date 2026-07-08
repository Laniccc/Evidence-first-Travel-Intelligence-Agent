#!/usr/bin/env python3
"""Manual smoke: Dianping review crawler."""

from __future__ import annotations

import argparse
import asyncio

import _bootstrap  # noqa: F401 — sys.path

from app.config import get_settings

DianpingReviewCrawlerTool = _bootstrap.import_tools_module("crawlers.dianping_crawler_tool").DianpingReviewCrawlerTool


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
    tool = DianpingReviewCrawlerTool(settings)
    print(f"enabled={settings.dianping_crawler_enabled and settings.enable_review_crawler_providers}")
    print(f"websearch={settings.dianping_websearch_signal_enabled and settings.mcp_search_enabled}")
    print(f"configured={tool.is_configured()}")
    print(f"command={tool.command or '(empty)'}")
    print(f"workdir={tool.workdir or '(empty)'}")

    evidence = await tool.run(
        place_name=args.place,
        city=args.city,
        country=args.country,
        query=args.place,
        claim_type="review_summary",
    )
    meta = tool.last_run_meta
    print(f"transport={meta.get('transport', 'unknown')}")
    print(f"success={meta.get('error') is None}")
    print(f"output_parse_status={meta.get('output_parse_status')}")
    print(f"count={len(evidence)}")
    print(f"summary={_summarize(evidence)}")
    if meta.get("error"):
        print(f"error={meta['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
