"""Public tools package — lazy registry export to avoid import cycles in smoke/scripts."""

from __future__ import annotations

__all__ = ["ToolRegistry", "TravelToolRegistry"]


def __getattr__(name: str):
    if name in __all__:
        from tools.registry import ToolRegistry, TravelToolRegistry

        return ToolRegistry if name == "ToolRegistry" else TravelToolRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
