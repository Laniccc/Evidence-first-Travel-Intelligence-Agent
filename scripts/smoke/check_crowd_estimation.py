#!/usr/bin/env python3
"""Manual smoke: composite crowd estimation provider."""

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
from tools.crowd.crowd_estimation_tool import CrowdEstimationTool
from tools.registry import TravelToolRegistry


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--place", required=True)
    parser.add_argument("--city", default=None)
    args = parser.parse_args()
    settings = get_settings()
    registry = TravelToolRegistry()
    tool = CrowdEstimationTool(settings, registry=registry)
    print(f"configured={tool.is_configured()}")
    evidence = await tool.run(place_name=args.place, city=args.city, country="China")
    print(f"count={len(evidence)} meta={tool.last_run_meta}")
    for ev in evidence[:1]:
        for claim in ev.claims:
            print(claim.claim_type.value, claim.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
