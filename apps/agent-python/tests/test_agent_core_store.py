import json
import sqlite3

from app.orchestration.agent_core_store import SQLiteRunStore
from app.orchestration.run_inspector import RunInspector


EXPECTED_TABLES = {
    "run",
    "phase_event",
    "execution_attempt",
    "evidence_record",
    "answer_claim",
    "citation_decision",
    "run_metric",
}


def test_run_store_has_only_the_auditable_runtime_tables(tmp_path):
    path = tmp_path / "runs.sqlite3"
    store = SQLiteRunStore(path)

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    assert tables == EXPECTED_TABLES


def test_inspect_by_query_id_returns_complete_timeline_without_raw_query(tmp_path):
    store = SQLiteRunStore(tmp_path / "runs.sqlite3")
    store.start_run(
        run_id="run-1",
        query_id="query-1",
        session_id="session-1",
        query="故宫开放时间",
    )
    store.append_phase_event(
        run_id="run-1", state="ingress", status="succeeded", attempt=1, output={"ok": True}
    )
    store.append_phase_event(
        run_id="run-1",
        state="evidence_evaluate",
        status="succeeded",
        attempt=1,
        output={"claim_decisions": []},
    )
    store.record_execution_attempt(
        run_id="run-1", state="hybrid_retrieve", attempt=1, status="recovered"
    )
    store.record_evidence(
        run_id="run-1", evidence_id="e-1", payload={"source_url": "https://example.test"}
    )
    store.record_answer_claim(
        run_id="run-1", claim_id="c-1", payload={"text": "八点开放"}
    )
    store.record_citation_decision(
        run_id="run-1", claim_id="c-1", status="supported", reason="valid"
    )
    store.record_metric(run_id="run-1", name="citation_precision", value=1.0)

    inspection = RunInspector(store).inspect("query-1")

    assert [item.state for item in inspection.timeline] == ["ingress", "evidence_evaluate"]
    assert inspection.run.session_id == "session-1"
    assert inspection.metrics == {"citation_precision": 1.0}
    assert "故宫开放时间" not in json.dumps(inspection.model_dump(mode="json"), ensure_ascii=False)
