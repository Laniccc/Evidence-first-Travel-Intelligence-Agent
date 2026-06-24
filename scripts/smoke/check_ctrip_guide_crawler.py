#!/usr/bin/env python3
"""Manual smoke: Ctrip guide crawler."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "apps" / "agent-python"
sys.path.insert(0, str(AGENT))
sys.path.insert(0, str(ROOT / "packages"))

from app.config import get_settings
from tools.crawlers.ctrip_crawler_tool import CtripGuideCrawlerTool


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default=None)
    args = parser.parse_args()
    settings = get_settings()
    tool = CtripGuideCrawlerTool(settings)
    print(f"configured={tool.is_configured()}")
    evidence = await tool.run(place_name=args.place, city=args.city, country="China")
    print(f"count={len(evidence)}")
    for ev in evidence[:2]:
        print(ev.claims[0].claim_type.value, str(ev.claims[0].value)[:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
