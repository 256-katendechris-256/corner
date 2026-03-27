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
    embedding vector(1536), -- OpenAI text-embedding-3-small
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- Scored and interpreted items
CREATE TABLE IF NOT EXISTS scored_items (
    id TEXT PRIMARY KEY,
    source_item_id TEXT REFERENCES source_items(id),
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
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
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