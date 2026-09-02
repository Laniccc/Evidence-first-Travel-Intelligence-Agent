"""Read-only query-id inspection facade for auditable Agent runs."""

from app.orchestration.agent_core_models import RunInspection
from app.orchestration.agent_core_store import SQLiteRunStore


class RunInspector:
    def __init__(self, store: SQLiteRunStore) -> None:
        self._store = store

    def inspect(self, query_id: str) -> RunInspection:
        return self._store.inspect(query_id)


__all__ = ["RunInspector"]
