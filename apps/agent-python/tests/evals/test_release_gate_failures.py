from copy import deepcopy
import json

import pytest

from evals.graders.promotion import grade_case_safety
from evals import runner


@pytest.mark.parametrize("state,actual", [
    ("knowledge_promote", {"outcome": "auto_publish"}),
    ("live_gap_fill", {"tool_calls": 5}),
    ("citation_guard", {"supported": True}),
    ("live_gap_fill", {"failure_code": None}),
])
def test_any_critical_case_failure_has_actionable_bad_case(state, actual):
    expected = {"knowledge_promote": {"outcome": "rejected"},
                "citation_guard": {"supported": False}}.get(state, {"tool_calls": 0, "failure_code": "tool_not_allowed"})
    row = {"case_id": "mutated-case", "state": state, "expected": expected,
           "actual": actual, "artifact_refs": ["suites/fixture/mutated-case"]}
    result = grade_case_safety({"fixture": {"cases": [row]}})
    assert not result["passed"]
    assert result["bad_cases"][0]["case_id"] == "mutated-case"
    assert set(("expected", "actual", "state", "failure_code", "artifact_refs")) <= result["bad_cases"][0].keys()


def test_old_operational_suites_also_block_release():
    cases = {
        "evidence_conflict": {"cases": [{"case_id": "conflict", "expected_conflict": True,
            "actual_conflict": False, "expected_source_count": 2, "retained_source_count": 1,
            "preferred_authority_ok": False}]},
        "failure_recovery": {"cases": [{"case_id": "recovery", "expected_outcome": "compose",
            "actual_outcome": "safe_failure", "attempt_count": 3, "logical_task_count": 2,
            "abstention_correct": False}]},
        "conversation": {"cases": [{"case_id": "conversation", "expected_terminal": "comparison",
            "actual_terminal": "comparison", "expected_attractions": ["a", "b"],
            "actual_attractions": ["a", "a"], "plan_isolation_ok": False}]},
    }
    assert {x["case_id"] for x in grade_case_safety(cases)["bad_cases"]} == {"conflict", "recovery", "conversation"}


def test_original_multiturn_cases_keep_their_expected_behavior():
    environment = runner._environment(profile="offline")
    try:
        result = runner._conversation_suite(environment[2])
        assert grade_case_safety({"conversation": result})["passed"]
    finally:
        environment[1].close()
        environment[0].cleanup()


def test_missing_cases_and_retrieval_provenance_fail_closed():
    result = grade_case_safety({"empty": {"cases": [], "min_cases": 8}, "retrieval": {"cases": [
        {"case_id": "missing-provenance", "metadata_filter_ok": True, "provenance_complete": False}]}})
    assert {r["case_id"] for r in result["bad_cases"]} == {"empty:insufficient_cases", "missing-provenance"}


def test_actual_cli_blocks_mutated_dataset(tmp_path, monkeypatch):
    # Keep the production CLI/gates/runners; only change one dataset's expectation.
    import evals.closure as closure
    original = closure.load_cases
    def mutated(name):
        rows = deepcopy(original(name))
        if name == "knowledge_promotion":
            rows[0]["expected"]["outcome"] = "rejected"
        return rows
    monkeypatch.setattr(closure, "load_cases", mutated)
    report = tmp_path / "mutation.json"
    assert runner.main(["--suite", "all", "--offline", "--fail-on-regression", "--report", str(report)]) == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["case_count"] >= 111
    assert any(row["case_id"] == "promotion-stable-address" for row in payload["bad_cases"])
