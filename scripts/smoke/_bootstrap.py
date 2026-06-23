"""Shared path bootstrap for smoke scripts."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "apps" / "agent-python"
PACKAGES = ROOT / "packages"

for path in (str(AGENT), str(PACKAGES)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from dotenv import load_dotenv

    load_dotenv(AGENT / ".env")
except ImportError:
    pass


def import_tools_module(module: str):
    """Import tools subpackage module without eager registry side effects."""
    return importlib.import_module(f"tools.{module}")
