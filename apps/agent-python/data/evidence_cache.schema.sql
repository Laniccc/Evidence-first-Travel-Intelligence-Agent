-- Evidence cache schema for mcp-sqlite (apps/agent-python/data/evidence_cache.db)
CREATE TABLE IF NOT EXISTS evidence_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    place_name TEXT,
    country TEXT,
    city TEXT,
    claim_type TEXT,
    claim_value TEXT,
    source_url TEXT,
    confidence REAL,
    retrieved_at TEXT DEFAULT (datetime('now')),
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS place_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_name TEXT NOT NULL,
    country TEXT,
    city TEXT,
    latitude REAL,
    longitude REAL,
    wikidata_id TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_trace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    tool_name TEXT,
    status TEXT,
    latency_ms REAL,
    created_at TEXT DEFAULT (datetime('now')),
    detail_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_evidence_session ON evidence_cache(session_id);
CREATE INDEX IF NOT EXISTS idx_evidence_place ON evidence_cache(place_name);
CREATE INDEX IF NOT EXISTS idx_place_name ON place_cache(place_name);
