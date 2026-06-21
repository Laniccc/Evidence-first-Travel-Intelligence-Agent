"""Load legacy agent runtime from backend/ (read-only; no backend modifications)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

_RUNTIME: dict[str, Any] | None = None
_STATE_MACHINE: Any | None = None
_PRESERVED_AGENT_MODULES = ("app.main", "app.contract", "app._legacy")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _backend_root() -> Path:
    return _repo_root() / "backend"


def _agent_python_root() -> Path:
    return _repo_root() / "apps" / "agent-python"


def load_legacy_runtime() -> tuple[type, Callable[..., Any], Callable[..., Any]]:
    """Return (TravelAgentStateMachine, get_settings, setup_logging)."""
    global _RUNTIME
    if _RUNTIME is not None:
        return (
            _RUNTIME["state_machine_cls"],
            _RUNTIME["get_settings"],
            _RUNTIME["setup_logging"],
        )

    preserved = {name: sys.modules[name] for name in _PRESERVED_AGENT_MODULES if name in sys.modules}
    for name in list(sys.modules):
        if name == "app" or name.startswith("app."):
            if name in preserved:
                continue
            del sys.modules[name]

    backend = str(_backend_root())
    agent_root = str(_agent_python_root())
    original_path = sys.path[:]
    sys.path[:] = [p for p in original_path if Path(p).resolve() != Path(agent_root).resolve()]
    if backend not in sys.path:
        sys.path.insert(0, backend)

    try:
        config_mod = importlib.import_module("app.config")
        logging_mod = importlib.import_module("app.logging_config")
        state_machine_mod = importlib.import_module("app.orchestrator.state_machine")
        _RUNTIME = {
            "state_machine_cls": state_machine_mod.TravelAgentStateMachine,
            "get_settings": config_mod.get_settings,
            "setup_logging": logging_mod.setup_logging,
        }
        return (
            _RUNTIME["state_machine_cls"],
            _RUNTIME["get_settings"],
            _RUNTIME["setup_logging"],
        )
    finally:
        sys.path[:] = original_path
        for name, module in preserved.items():
            sys.modules[name] = module


def get_settings():
    _, get_settings_fn, setup_logging_fn = load_legacy_runtime()
    settings = get_settings_fn()
    setup_logging_fn(settings.log_level)
    return settings


def get_state_machine():
    global _STATE_MACHINE
    if _STATE_MACHINE is None:
        sm_cls, _, _ = load_legacy_runtime()
        _STATE_MACHINE = sm_cls()
    return _STATE_MACHINE
