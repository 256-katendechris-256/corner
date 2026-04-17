# Corner — AI market intelligence pipeline

End-to-end flow: **collect** sources → **normalise** (embed + dedupe) → **score** with an LLM → **synthesise** a markdown digest → **human review** (FastAPI + Next.js) → optional **Slack** publish. Postgres + **pgvector** stores sources, scored rows, run logs, and published digests.

## Repository layout

| Path | Role |
|------|------|
| `agent/config.py` | `pydantic-settings` — env vars, `similarity_threshold`, API keys |
| `agent/ingestion/tier1.py` | Tier-1 pages + RSS (full article fetch where possible) |
| `agent/ingestion/rss.py` | Tier-2 newsletters / blogs |
| `agent/ingestion/web.py` | `httpx` fetch + HTML text extraction; **Firecrawl** fallback on 403 |
| `agent/normalisation/` | `SourceItem` / `ScoredItem` schemas, local embeddings, DB I/O |
| `agent/pipeline/` | LangGraph: `nodes.py`, `runner.py`, `state.py` |
| `agent/scoring/scorer.py` | Groq JSON scoring + RAG context + Langfuse trace metadata |
| `agent/observability/tracer.py` | Langfuse v4 spans for scoring and full runs |
| `agent/publishing/approval_api.py` | REST: draft, approve/reject, stats, run pipeline (background thread) |
| `agent/publishing/slack.py` | Webhook publish |
| `db/schema.py` | DDL + `python -m db.schema` to initialise |
| `frontend/` | Next.js dashboard (stats, history, review, run pipeline) |

## Run locally

1. PostgreSQL with `pgvector`, set `postgres_url` in `.env`.
2. `python -m db.schema` — create tables.
3. Pipeline: `python -m agent.pipeline.runner` (writes `/tmp/digest_draft.json`).
4. API: `uvicorn agent.publishing.approval_api:app --reload --port 8000`.
5. UI: `cd frontend && npm run dev` — set `NEXT_PUBLIC_API_URL` if the API is not on `localhost:8000`.

## Configuration (`.env`)

Required: `postgres_url`, `groq_api_key`. Optional: `slack_webhook_url`, `firecrawl_api_key`, Langfuse keys, `similarity_threshold` (dedup; default 0.92).
