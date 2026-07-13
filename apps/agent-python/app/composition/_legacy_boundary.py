"""Dynamic boundary for final dependencies that composition cannot import eagerly."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from typing import Any


def legacy_attr(module_path: str, attr_name: str) -> Any:
    return getattr(legacy_module(module_path), attr_name)


def final_attr(module_path: str, attr_name: str) -> Any:
    """Resolve a final-layer dependency when static imports would invert ownership."""
    return getattr(legacy_module(module_path), attr_name)


@lru_cache(maxsize=None)
def legacy_module(module_path: str) -> Any:
    return import_module(module_path)


def legacy_integration_attr(*parts: str) -> Any:
    *module_parts, attr_name = parts
    return legacy_attr(".".join(["app", "integrations", *module_parts]), attr_name)


def legacy_tool_attr(*parts: str) -> Any:
    *module_parts, attr_name = parts
    return legacy_attr(".".join(["tools", *module_parts]), attr_name)
