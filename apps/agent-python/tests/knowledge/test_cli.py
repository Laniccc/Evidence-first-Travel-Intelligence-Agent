from datetime import UTC, datetime
from pathlib import Path

from app.evidence.knowledge.cli import main
from app.evidence.knowledge.repository import KnowledgeRepository


def test_seed_accepts_checked_in_eval_fixture(tmp_path: Path) -> None:
    database = tmp_path / "knowledge.sqlite3"
    fixture = Path(__file__).parents[2] / "evals" / "fixtures" / "knowledge.json"

    exit_code = main(
        [
            "seed",
            "--db",
            str(database),
            "--fixture",
            str(fixture),
            "--auto-publish",
        ]
    )

    repository = KnowledgeRepository(database)
    chunks = repository.list_active_chunks(datetime.now(UTC))
    assert exit_code == 0
    assert {chunk.attraction_id for chunk in chunks} == {
        "forbidden-city",
        "summer-palace",
        "temple-of-heaven",
        "badaling",
        "shanghai-museum",
        "west-lake",
        "terracotta-army",
        "jiuzhaigou",
    }
    assert len(chunks) == 64
