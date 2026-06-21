"""agent-python application package."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_packages_on_path() -> None:
    packages_root = Path(__file__).resolve().parents[3] / "packages"
    path = str(packages_root)
    if path not in sys.path:
        sys.path.insert(0, path)


_ensure_packages_on_path()
