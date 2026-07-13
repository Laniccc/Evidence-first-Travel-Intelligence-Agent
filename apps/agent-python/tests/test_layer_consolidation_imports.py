import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"

TARGET_LAYERS = [
    "api",
    "contracts",
    "context",
    "understanding",
    "planning",
    "execution",
    "tools",
    "integrations",
    "evidence",
    "composition",
    "orchestration",
    "governance",
    "observability",
]

RETIRED_PACKAGES = (
    "agents",
    "orchestrator",
    "schemas",
    "tool_gateway",
    "storage",
    "catalog",
    "prompts",
    "policies",
)

TASK_20Q_LEGACY_HELPERS = frozenset(
    {
        "answer_mode_router",
        "claim_family_registry",
        "claim_gap_fill_planner",
        "claim_policy_registry",
        "claim_tool_policy",
        "information_need_aliases",
        "intent_profile_deriver",
        "intent_s7_policy",
        "intent_strategy_registry",
        "lookup_need_aliases",
    }
)

TASK_20R_LEGACY_HELPERS = frozenset(
    {
        "fact_lookup_anchor_policy",
        "fact_lookup_policy",
        "fact_lookup_task_orchestration",
        "lookup_entity_resolution_policy",
        "lookup_query_objectives",
        "lookup_research_chain",
        "search_query_rewriter",
        "retrieval_attempt_ledger",
    }
)

TASK_20S_LEGACY_HELPERS = frozenset(
    {
        "baidu_poi_taxonomy",
        "geo_fact_gazetteer",
        "mcp_tool_arguments",
        "nearby_anchor_policy",
        "nearby_category_registry",
        "nearby_enrichment_policy",
        "nearby_recommendation_policy",
        "nearby_task_orchestration",
        "s5_diversified_tool_selector",
        "s5_poi_anchor_policy",
    }
)

TASK_20T_LEGACY_HELPERS = frozenset(
    {
        "ticket_area_policy",
        "ticket_lookup_attempt_tracker",
        "ticket_lookup_helpers",
        "ticket_lookup_policy",
        "ticket_price_audit",
        "ticket_price_extractor",
        "ticket_price_query_ladder",
        "ticket_product_policy",
        "ticket_relevance_policy",
        "s5_tool_attempt_ledger",
    }
)

TASK_20U_LEGACY_HELPERS = frozenset(
    {
        "evidence_ladder",
        "evidence_signal_utils",
        "evidence_usage_role",
        "official_candidate_bridge",
        "official_chain_policy",
        "official_source_judgement",
        "official_source_search_templates",
        "opening_hours_extractor",
        "peak_elevation_extraction",
        "search_snippet_policy",
    }
)

TASK_20V_LEGACY_HELPERS = frozenset(
    {
        "claim_compiler",
        "comparison_helpers",
        "composition_preflight",
        "non_lookup_task_chains",
        "place_disambiguation_guard",
        "user_need_residual",
        "composer_subagent",
        "subagents.composer_subagent",
    }
)

RETIRED_DYNAMIC_HELPER_CALLS = frozenset(
    {f"legacy_{layer}_attr" for layer in ("agent", "orchestrator", "schema")}
    | {"_" + "_".join(("legacy", "orchestrator"))}
)


# Task 11 removes context entries.
# Task 12 removes understanding entries.
# Task 13 removes planning entries.
# Task 14 removes execution entries.
# Task 15 removes integrations entries.
# Task 16 removes evidence entries.
# Task 17 removes composition entries.
# Task 18 removes orchestration entries.
# Task 19 removes governance and observability entries.
ALLOWED_RETIRED_IMPORTS_BY_TASK = {
    "Task 11 context": set(),
    "Task 12 understanding": set(),
    "Task 13 planning": set(),
    "Task 14 execution": set(),
    "Task 15 integrations": set(),
    "Task 16 evidence": set(),
    "Task 17 composition": set(),
    "Task 18 orchestration": set(),
    "Task 19 governance_observability": set(),
}

TARGET_LAYER_IMPORT_RULES = {
    "api": {"contracts", "orchestration", "observability", "config"},
    "contracts": set(),
    "context": {"contracts"},
    "understanding": {"contracts", "context"},
    "planning": {"understanding", "context", "contracts", "evidence"},
    "execution": {"planning", "tools", "integrations", "observability"},
    "tools": {"contracts", "evidence"},
    "integrations": {"config"},
    "evidence": {"contracts", "evidence"},
    "composition": {"evidence", "contracts"},
    "orchestration": {
        "api",
        "contracts",
        "context",
        "understanding",
        "planning",
        "execution",
        "tools",
        "integrations",
        "evidence",
        "composition",
        "governance",
        "observability",
    },
    "governance": set(),
    "observability": {"contracts"},
}

# Task 10 removes api/contracts schema violations.
# Task 11 removes context violations.
# Task 12 removes understanding violations.
# Task 13 removes planning violations.
# Task 14 removes execution violations.
# Task 15 removes integration adapter violations.
# Task 16 removes evidence violations.
# Task 17 removes composition violations.
# Task 18 removes orchestration violations.
# Task 19 removes governance and observability violations.
ALLOWED_LAYER_IMPORTS_BY_TASK = {
    "Task 10 contracts_api": set(),
    "Task 11 context": set(),
    "Task 12 understanding": set(),
    "Task 13 planning": set(),
    "Task 14 execution": set(),
    "Task 15 integrations": set(),
    "Task 16 evidence": set(),
    "Task 17 composition": set(),
    "Task 18 orchestration": set(),
    "Task 19 governance_observability": set(),
}


def test_target_layers_only_use_known_retired_imports():
    allowed = set().union(*ALLOWED_RETIRED_IMPORTS_BY_TASK.values())
    found = list(_retired_imports())
    unexpected = [entry for entry in found if entry not in allowed]
    stale_allowlist = sorted(allowed.difference(found))

    assert not unexpected, "Unexpected retired imports:\n" + "\n".join(unexpected)
    assert not stale_allowlist, "Remove stale retired-import allowlist entries:\n" + "\n".join(stale_allowlist)


def test_target_layers_only_use_allowed_layer_dependencies():
    allowed = set().union(*ALLOWED_LAYER_IMPORTS_BY_TASK.values())
    found = list(_layer_import_violations())
    unexpected = [entry for entry in found if entry not in allowed]
    stale_allowlist = sorted(allowed.difference(found))

    assert not unexpected, "Unexpected target-layer dependency violations:\n" + "\n".join(unexpected)
    assert not stale_allowlist, "Remove stale target-layer dependency allowlist entries:\n" + "\n".join(stale_allowlist)


def test_target_layers_have_no_task_20q_legacy_helper_bridges():
    found = list(_legacy_helper_bridges(TASK_20Q_LEGACY_HELPERS))

    assert not found, "Task 20Q legacy helper bridges:\n" + "\n".join(found)


def test_target_layers_have_no_task_20r_legacy_helper_bridges():
    found = list(_legacy_helper_bridges(TASK_20R_LEGACY_HELPERS))

    assert not found, "Task 20R legacy helper bridges:\n" + "\n".join(found)


def test_target_layers_have_no_task_20s_legacy_helper_bridges():
    found = list(_legacy_helper_bridges(TASK_20S_LEGACY_HELPERS))

    assert not found, "Task 20S legacy helper bridges:\n" + "\n".join(found)


def test_target_layers_have_no_task_20t_legacy_helper_bridges():
    found = list(_legacy_helper_bridges(TASK_20T_LEGACY_HELPERS))

    assert not found, "Task 20T legacy helper bridges:\n" + "\n".join(found)


def test_target_layers_have_no_task_20u_legacy_helper_bridges():
    found = list(_legacy_helper_bridges(TASK_20U_LEGACY_HELPERS))

    assert not found, "Task 20U legacy helper bridges:\n" + "\n".join(found)


def test_target_layers_have_no_task_20v_legacy_helper_bridges():
    found = list(_legacy_helper_bridges(TASK_20V_LEGACY_HELPERS))

    assert not found, "Task 20V legacy helper bridges:\n" + "\n".join(found)


def test_target_layers_have_no_retired_dynamic_helper_calls():
    found = list(_retired_dynamic_helper_calls())

    assert not found, "Retired dynamic helper calls:\n" + "\n".join(found)


def _retired_imports():
    retired_prefixes = tuple(f"app.{package}" for package in RETIRED_PACKAGES)
    for layer in TARGET_LAYERS:
        layer_root = APP_ROOT / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*.py")):
            relative = path.relative_to(APP_ROOT).as_posix()
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                stripped = line.strip()
                if stripped.startswith("from ") or stripped.startswith("import "):
                    if any(f" {prefix}" in f" {stripped}" for prefix in retired_prefixes):
                        yield f"{relative}|{stripped}"


def _layer_import_violations():
    for layer in TARGET_LAYERS:
        layer_root = APP_ROOT / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*.py")):
            relative = path.relative_to(APP_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for module_name in _imported_app_modules(tree):
                imported_layer = module_name.split(".")[1]
                if imported_layer == layer:
                    continue
                if imported_layer in TARGET_LAYER_IMPORT_RULES[layer]:
                    continue
                yield f"{relative}|{module_name}"


def _legacy_helper_bridges(helper_names):
    for layer in TARGET_LAYERS:
        layer_root = APP_ROOT / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*.py")):
            relative = path.relative_to(APP_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                if node.func.id not in RETIRED_DYNAMIC_HELPER_CALLS or not node.args:
                    continue
                helper = node.args[0]
                if isinstance(helper, ast.Constant) and helper.value in helper_names:
                    yield f"{relative}|{helper.value}"


def _retired_dynamic_helper_calls():
    for layer in TARGET_LAYERS:
        layer_root = APP_ROOT / layer
        if not layer_root.exists():
            continue
        for path in sorted(layer_root.rglob("*.py")):
            relative = path.relative_to(APP_ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in RETIRED_DYNAMIC_HELPER_CALLS:
                        yield f"{relative}|{node.func.id}"


def _imported_app_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app."):
            yield node.module
