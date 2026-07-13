"""Dynamic boundary for final integrations that cannot be imported eagerly."""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from typing import Any


@lru_cache(maxsize=None)
def legacy_module(module_path: str) -> Any:
    return import_module(module_path)


def legacy_attr(module_path: str, attr_name: str) -> Any:
    return getattr(legacy_module(module_path), attr_name)


def legacy_config_attr(attr_name: str) -> Any:
    return legacy_attr(".".join(["app", "config"]), attr_name)
