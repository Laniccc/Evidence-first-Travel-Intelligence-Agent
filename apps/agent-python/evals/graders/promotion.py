"""Per-case safety gates: aggregate success never hides an individual unsafe result."""


def _expectations(suite, row):
    if suite == "retrieval":
        return {"metadata_filter_ok": True, "provenance_complete": True}, row
    if "expected" in row:
        return row["expected"], row.get("actual", {})
    expected, actual = {}, {}
    for key, value in row.items():
        if key.startswith("expected_"):
            name = key.removeprefix("expected_")
            expected[name] = value
            actual[name] = row.get("actual_" + name)
    for key in ("preferred_authority_ok", "abstention_correct", "plan_isolation_ok"):
        if key in row:
            expected[key], actual[key] = True, row[key]
    if "expected_source_count" in row:
        actual["source_count"] = row["retained_source_count"]
    for key, limit in (("attempt_count", 2), ("logical_task_count", 1), ("illegal_transition_count", 0)):
        if key in row:
            expected[key + "_bounded"], actual[key + "_bounded"] = True, row[key] <= limit
    if suite == "versioning":
        expected.update(returned=row["status"] == "active")
        actual.update(returned=row["returned"])
        if row["status"] != "active":
            expected["rejected_by_post_filter"] = True
            actual["rejected_by_post_filter"] = row["rejected_by_post_filter"]
    return expected, actual


def grade_case_safety(suites):
    bad_cases = []
    for name, suite in suites.items():
        if len(suite["cases"]) < suite.get("min_cases", 1):
            bad_cases.append({"case_id": name + ":insufficient_cases", "expected": {"min_cases": suite.get("min_cases", 1)},
                "actual": {"case_count": len(suite["cases"])}, "state": "dataset",
                "failure_code": "insufficient_cases", "artifact_refs": [f"suites/{name}/cases"]})
        for row in suite["cases"]:
            expected, actual = _expectations(name, row)
            if not expected or any(actual.get(key) != value for key, value in expected.items()):
                bad_cases.append({"case_id": row["case_id"], "expected": expected, "actual": actual,
                    "state": row.get("state", name), "failure_code": actual.get("failure_code") or "case_assertion_failed",
                    "artifact_refs": row.get("artifact_refs", [f"suites/{name}/cases/{row['case_id']}"])})
    return {"passed": not bad_cases, "bad_cases": bad_cases}
