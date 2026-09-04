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

CREATE TABLE IF NOT EXISTS index_generation (
    generation_id TEXT PRIMARY KEY,
    corpus_version TEXT NOT NULL,
    embedding_model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'building', 'active', 'failed', 'superseded')
    ),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    indexed_chunk_count INTEGER NOT NULL DEFAULT 0,
    failed_chunk_count INTEGER NOT NULL DEFAULT 0,
    deleted_chunk_count INTEGER NOT NULL DEFAULT 0,
    failure_code TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_index_generation_active
ON index_generation(status)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_index_generation_corpus_model
ON index_generation(corpus_version, embedding_model, status);

CREATE TABLE IF NOT EXISTS chunk_index_state (
    generation_id TEXT NOT NULL REFERENCES index_generation(generation_id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES fact_chunk(chunk_id) ON DELETE CASCADE,
    qdrant_point_id TEXT,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'indexed', 'failed', 'deleted')
    ),
    last_attempt_at TEXT NOT NULL,
    failure_code TEXT,
    PRIMARY KEY (generation_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_index_state_status
ON chunk_index_state(generation_id, status);

-- Promotion outbox: same database and transaction as authoritative knowledge.
CREATE TABLE IF NOT EXISTS promotion_decision (
    decision_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    query_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason_codes TEXT NOT NULL,
    evidence_refs TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    version_id TEXT REFERENCES document_version(version_id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_sync_job (
    job_id TEXT PRIMARY KEY,
    dedupe_key TEXT NOT NULL UNIQUE,
    version_id TEXT NOT NULL REFERENCES document_version(version_id),
    status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    next_attempt_at TEXT,
    last_failure_code TEXT,
    generation_id TEXT,
    run_id TEXT NOT NULL,
    query_id TEXT NOT NULL,
    trace_id TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_index_job_due ON index_sync_job(status, next_attempt_at);
