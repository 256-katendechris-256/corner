# db/schema.py
import psycopg2
from agent.config import settings

CREATE_SQL = """
-- Enable pgvector (idempotent)
CREATE EXTENSION IF NOT EXISTS vector;

-- Raw ingested items (one row per source article)
CREATE TABLE IF NOT EXISTS source_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_tier TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    canonical_url TEXT NOT NULL,
    raw_content TEXT,
    key_excerpt TEXT,
    embedding vector(384),
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Scored and interpreted items
CREATE TABLE IF NOT EXISTS scored_items (
    id TEXT PRIMARY KEY,
    source_item_id TEXT REFERENCES source_items(id),
    run_id TEXT,
    relevance FLOAT,
    novelty FLOAT,
    urgency FLOAT,
    confidence FLOAT,
    what_changed TEXT,
    why_it_matters TEXT,
    recommended_action TEXT,
    impact_tags TEXT[],
    approved BOOLEAN DEFAULT FALSE,
    approved_summary TEXT,
    trace_id TEXT,
    scored_at TIMESTAMPTZ DEFAULT NOW()
);

-- Run logs for observability
CREATE TABLE IF NOT EXISTS run_logs (
    id SERIAL PRIMARY KEY,
    run_id TEXT,
    stage TEXT,
    status TEXT,
    item_count INTEGER DEFAULT 0,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Published digests (persists after draft file is deleted)
CREATE TABLE IF NOT EXISTS published_digests (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    digest_text TEXT NOT NULL,
    item_count INTEGER DEFAULT 0,
    published_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migration: add run_id to scored_items if missing
DO $$ BEGIN
    ALTER TABLE scored_items ADD COLUMN IF NOT EXISTS run_id TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Migration: add item_count to run_logs if missing
DO $$ BEGIN
    ALTER TABLE run_logs ADD COLUMN IF NOT EXISTS item_count INTEGER DEFAULT 0;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;
"""

def init_db():
    conn = psycopg2.connect(settings.postgres_url)
    with conn.cursor() as cur:
        cur.execute(CREATE_SQL)
    conn.commit()
    conn.close()
    print('Database initialised.')

if __name__ == '__main__':
    init_db()