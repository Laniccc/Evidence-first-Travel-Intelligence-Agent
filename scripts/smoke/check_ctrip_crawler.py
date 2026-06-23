#!/usr/bin/env python3
"""Manual smoke: Ctrip review crawler subprocess wrapper."""

from __future__ import annotations

import argparse
import asyncio

from _bootstrap import AGENT  # noqa: F401

from app.config import get_settings
from tools.crawlers.ctrip_crawler_tool import CtripReviewCrawlerTool


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
    tool = CtripReviewCrawlerTool(settings)
    print(f"enabled={settings.ctrip_crawler_enabled and settings.enable_review_crawler_providers}")
    print(f"configured={tool.is_configured()}")
    print(f"command={tool.command or '(empty)'}")

    evidence = await tool.run_query(
        args.place, args.city, args.country, query=args.place, claim_type="review_summary"
    )
    meta = tool.last_run_meta
    print(f"success={meta.get('status') == 'ok'}")
    print(f"count={len(evidence)}")
    print(f"summary={_summarize(evidence)}")
    if meta.get("error"):
        print(f"error={meta['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
