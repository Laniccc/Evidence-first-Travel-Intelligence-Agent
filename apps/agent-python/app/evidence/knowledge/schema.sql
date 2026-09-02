PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS attraction (
    attraction_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    city TEXT,
    country TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_document (
    source_id TEXT PRIMARY KEY,
    attraction_id TEXT NOT NULL REFERENCES attraction(attraction_id),
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('official', 'structured', 'search', 'forum', 'model_prior')
    ),
    authority_score REAL NOT NULL CHECK (authority_score >= 0 AND authority_score <= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (attraction_id, url)
);

CREATE TABLE IF NOT EXISTS document_version (
    version_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_document(source_id),
    content_hash TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'active', 'superseded', 'expired', 'rejected')
    ),
    fetched_at TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    published_at TEXT,
    supersedes_version_id TEXT REFERENCES document_version(version_id),
    rejection_reason TEXT,
    UNIQUE (source_id, content_hash)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_document_version_active_source
ON document_version(source_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_document_version_source_status
ON document_version(source_id, status);

CREATE INDEX IF NOT EXISTS idx_document_version_valid_to
ON document_version(valid_to, status);

CREATE TABLE IF NOT EXISTS fact_chunk (
    chunk_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES document_version(version_id) ON DELETE CASCADE,
    attraction_id TEXT NOT NULL REFERENCES attraction(attraction_id),
    fact_type TEXT NOT NULL CHECK (
        fact_type IN (
            'opening_hours', 'ticket_price', 'reservation', 'transport',
            'accessibility', 'visitor_notice', 'general_description'
        )
    ),
    content TEXT NOT NULL,
    locator TEXT,
    language TEXT NOT NULL DEFAULT 'zh-CN'
);

CREATE INDEX IF NOT EXISTS idx_fact_chunk_attraction_type
ON fact_chunk(attraction_id, fact_type);

CREATE VIRTUAL TABLE IF NOT EXISTS fact_chunk_fts USING fts5(
    chunk_id UNINDEXED,
    attraction_id UNINDEXED,
    fact_type UNINDEXED,
    content,
    tokenize = 'unicode61'
);

CREATE TRIGGER IF NOT EXISTS fact_chunk_ai AFTER INSERT ON fact_chunk BEGIN
    INSERT INTO fact_chunk_fts(chunk_id, attraction_id, fact_type, content)
    VALUES (new.chunk_id, new.attraction_id, new.fact_type, new.content);
END;

CREATE TRIGGER IF NOT EXISTS fact_chunk_ad AFTER DELETE ON fact_chunk BEGIN
    DELETE FROM fact_chunk_fts WHERE chunk_id = old.chunk_id;
END;

CREATE TRIGGER IF NOT EXISTS fact_chunk_au AFTER UPDATE ON fact_chunk BEGIN
    DELETE FROM fact_chunk_fts WHERE chunk_id = old.chunk_id;
    INSERT INTO fact_chunk_fts(chunk_id, attraction_id, fact_type, content)
    VALUES (new.chunk_id, new.attraction_id, new.fact_type, new.content);
END;

CREATE TABLE IF NOT EXISTS retrieval_log (
    retrieval_id TEXT PRIMARY KEY,
    query_id TEXT,
    query_text_hash TEXT NOT NULL,
    attraction_ids_json TEXT NOT NULL,
    fact_types_json TEXT NOT NULL,
    top_k INTEGER NOT NULL,
    result_chunk_ids_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
