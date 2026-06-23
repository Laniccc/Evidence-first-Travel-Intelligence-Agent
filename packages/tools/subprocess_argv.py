"""Resolve CLI executables for subprocess on Windows (.cmd shims)."""

from __future__ import annotations

import shutil
import sys


def resolve_executable_argv(argv: list[str]) -> list[str]:
    if not argv or sys.platform != "win32":
        return argv
    resolved = shutil.which(argv[0])
    if resolved:
        return [resolved, *argv[1:]]
    return argv
