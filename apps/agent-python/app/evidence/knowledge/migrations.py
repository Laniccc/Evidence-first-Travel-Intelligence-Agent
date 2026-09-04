"""Idempotent, transactional migration retaining old hashes, IDs and FTS rows."""
import sqlite3


def migrate(path):
    with sqlite3.connect(path) as db:
        # SQLite's documented table rebuild preserves foreign key target names.
        db.execute("PRAGMA foreign_keys = OFF")
        db.execute("BEGIN IMMEDIATE")
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name='source_document'").fetchone()[0]
        if "UNIQUE (attraction_id, url)" in sql:
            replacement = sql.replace("source_document", "source_document_v2", 1).replace(
                ",\n    UNIQUE (attraction_id, url)", "")
            db.execute(replacement)
            db.execute("INSERT INTO source_document_v2 SELECT * FROM source_document")
            db.execute("DROP TABLE source_document")
            db.execute("ALTER TABLE source_document_v2 RENAME TO source_document")
        columns = {row[1] for row in db.execute("PRAGMA table_info(document_version)")}
        for name, kind in {"hash_version": "INTEGER NOT NULL DEFAULT 1", "payload_hash": "TEXT",
                           "source_url": "TEXT", "source_title": "TEXT", "source_type": "TEXT",
                           "source_authority": "REAL"}.items():
            if name not in columns:
                db.execute(f"ALTER TABLE document_version ADD COLUMN {name} {kind}")
        # Freeze provenance of existing versions before any future source update.
        db.execute("""UPDATE document_version SET
            source_url=(SELECT url FROM source_document WHERE source_id=document_version.source_id),
            source_title=(SELECT title FROM source_document WHERE source_id=document_version.source_id),
            source_type=(SELECT source_type FROM source_document WHERE source_id=document_version.source_id),
            source_authority=(SELECT authority_score FROM source_document WHERE source_id=document_version.source_id)
            WHERE source_url IS NULL""")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("migration_foreign_key_check_failed")
        db.execute("PRAGMA user_version = 2")
