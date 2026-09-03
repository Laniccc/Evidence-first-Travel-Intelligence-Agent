"""Hard gate for the deliberately bounded portfolio product."""

from __future__ import annotations

import ast
from enum import StrEnum
from pathlib import Path

from app.evidence.knowledge.models import FactType


APP_ROOT = Path(__file__).resolve().parents[2] / "app"


class SupportedTask(StrEnum):
    FACT_QUERY = "fact_query"
    SUITABILITY = "suitability"
    COMPARISON = "comparison"
    CLARIFICATION = "clarification"


SUPPORTED_TASKS = {task.value for task in SupportedTask}
RETIRED_RUNTIME_MARKERS = {
    "itinerary",
    "nearby",
    "crowd_estimation",
    "review_crawler",
    "ticket_crawler",
    "neo4j",
    "graph_rag",
    "graph-rag",
}


def _runtime_surface_files() -> list[Path]:
    return sorted(
        path
        for path in APP_ROOT.rglob("*.py")
        if path.name == "config.py"
        or "registry" in path.stem
        or path.stem in {"routes", "router", "tool_router"}
    )


def _import_targets(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            targets.append(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"import_module", "_module"}
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            targets.append(node.args[0].value)
    return targets


def test_supported_product_scope_is_intentionally_small():
    assert SUPPORTED_TASKS == {
        "fact_query",
        "suitability",
        "comparison",
        "clarification",
    }


def test_retired_capabilities_are_absent_from_runtime_surfaces():
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        for target in _import_targets(path):
            normalized = target.lower().replace("-", "_")
            for marker in RETIRED_RUNTIME_MARKERS:
                if marker.replace("-", "_") in normalized:
                    violations.append(f"import:{relative}:{target}")

    for path in _runtime_surface_files():
        relative = path.relative_to(APP_ROOT).as_posix()
        normalized = path.read_text(encoding="utf-8-sig").lower()
        for marker in RETIRED_RUNTIME_MARKERS:
            if marker in normalized:
                violations.append(f"surface:{relative}:{marker}")

    assert violations == []


def test_ticket_price_remains_a_managed_knowledge_fact():
    assert FactType.TICKET_PRICE.value == "ticket_price"
