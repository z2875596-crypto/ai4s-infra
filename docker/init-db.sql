-- AI4S Infrastructure — database initialization
-- Run once when PostgreSQL container starts for the first time

-- Data catalog tables
CREATE TABLE IF NOT EXISTS catalog_datasets (
    name            TEXT PRIMARY KEY,
    description     TEXT NOT NULL DEFAULT '',
    owner           TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    format          TEXT NOT NULL DEFAULT 'parquet',
    tags            TEXT[] DEFAULT '{}',
    row_count       BIGINT DEFAULT 0,
    size_bytes      BIGINT DEFAULT 0,
    quality_score   REAL DEFAULT 1.0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    deprecated_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS catalog_columns (
    dataset_name    TEXT REFERENCES catalog_datasets(name) ON DELETE CASCADE,
    column_name     TEXT NOT NULL,
    dtype           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    nullable        BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (dataset_name, column_name)
);

-- Lineage edges
CREATE TABLE IF NOT EXISTS lineage_edges (
    edge_id     TEXT PRIMARY KEY,
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    step_type   TEXT NOT NULL,
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    metadata    JSONB DEFAULT '{}',
    run_id      TEXT
);
CREATE INDEX IF NOT EXISTS idx_lineage_source ON lineage_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_lineage_target ON lineage_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_lineage_type ON lineage_edges(step_type);

-- Feedback items (RLHF)
CREATE TABLE IF NOT EXISTS feedback_items (
    item_id         TEXT PRIMARY KEY,
    prompt          TEXT NOT NULL,
    response_a      TEXT NOT NULL,
    response_b      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    annotation      TEXT,
    annotator_id    TEXT,
    confidence      REAL DEFAULT 1.0,
    annotated_at    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- HPC job history
CREATE TABLE IF NOT EXISTS job_history (
    job_id          TEXT NOT NULL,
    connector       TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'pending',
    partition       TEXT NOT NULL DEFAULT '',
    nodes           INT DEFAULT 1,
    gpus            INT DEFAULT 0,
    submit_time     TIMESTAMPTZ DEFAULT NOW(),
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    user_name       TEXT DEFAULT 'unknown',
    project         TEXT DEFAULT 'default',
    PRIMARY KEY (job_id, connector)
);

-- HPC scheduling events
CREATE TABLE IF NOT EXISTS scheduling_events (
    id              SERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    job_id          TEXT,
    connector       TEXT,
    detail          TEXT,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sched_events_ts ON scheduling_events(timestamp DESC);

-- Alerts history
CREATE TABLE IF NOT EXISTS alerts (
    alert_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'info',
    source          TEXT NOT NULL DEFAULT 'ai4s-hpc',
    metadata        JSONB DEFAULT '{}',
    acknowledged    BOOLEAN DEFAULT FALSE,
    resolved        BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(created_at DESC);

-- Insert default AI4S user
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ai4s') THEN
        -- Role already created by POSTGRES_USER env var
    END IF;
END $$;

-- Grant permissions
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ai4s;
