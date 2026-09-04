import sqlite3

import pytest

from app.orchestration.agent_core_store import SQLiteRunStore


def test_audit_connection_closes_after_transaction_and_rollback(tmp_path):
    store = SQLiteRunStore(tmp_path / "run.db")
    with store._connect() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError):
        with store._connect() as failed:
            failed.execute("CREATE TABLE IF NOT EXISTS example (id TEXT)")
            failed.execute("INSERT INTO example VALUES ('rollback')")
            raise RuntimeError("fault")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed.execute("SELECT 1")
    with store._connect() as fresh:
        assert fresh.execute("SELECT count(*) FROM example").fetchone()[0] == 0
