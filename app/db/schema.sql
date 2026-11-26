CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    ats_type TEXT NOT NULL CHECK (ats_type IN ('greenhouse', 'lever', 'ashby', 'remotive')),
    board_slug TEXT NOT NULL,
    domain TEXT,
    median_days_open REAL,
    UNIQUE (ats_type, board_slug)
);

CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    is_remote BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT NOT NULL,
    apply_url TEXT,
    content_hash CHAR(64) NOT NULL,
    embedding vector(384),
    tsv tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(location, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'C')
    ) STORED,
    first_seen DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen DATE NOT NULL DEFAULT CURRENT_DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (source, external_id)
);

CREATE TABLE job_snapshots (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    seen_on DATE NOT NULL,
    content_hash CHAR(64) NOT NULL,
    title TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (job_id, seen_on)
);

CREATE TABLE job_events (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('appeared', 'edited', 'disappeared', 'reappeared')),
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ghost_scores (
    job_id BIGINT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    score REAL NOT NULL,
    features JSONB NOT NULL,
    model_version TEXT NOT NULL
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    skills TEXT[] NOT NULL DEFAULT '{}',
    target_roles TEXT[] NOT NULL DEFAULT '{}',
    locations TEXT[] NOT NULL DEFAULT '{}',
    yoe REAL,
    resume_text TEXT,
    embedding vector(384)
);

CREATE TABLE interactions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('shown', 'click', 'like', 'dislike', 'applied')),
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    rolling_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    conv_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    tool_calls JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE eval_queries (
    id SERIAL PRIMARY KEY,
    text TEXT NOT NULL
);

CREATE TABLE eval_labels (
    query_id INT NOT NULL REFERENCES eval_queries(id) ON DELETE CASCADE,
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    grade SMALLINT NOT NULL CHECK (grade BETWEEN 0 AND 2),
    PRIMARY KEY (query_id, job_id)
);

CREATE TABLE eval_runs (
    id SERIAL PRIMARY KEY,
    config JSONB NOT NULL,
    metrics JSONB NOT NULL,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_embedding_hnsw ON jobs USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_jobs_tsv_gin ON jobs USING gin (tsv);
CREATE INDEX idx_jobs_active_last_seen ON jobs (is_active, last_seen);
CREATE INDEX idx_job_events_job_id_at ON job_events (job_id, at DESC);
