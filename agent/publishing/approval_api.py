# agent/publishing/approval_api.py
import json
import os
import logging
import threading
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
import psycopg2.extras
from agent.config import settings
from agent.publishing.slack import publish_to_slack
from agent.normalisation.normaliser import save_published_digest

logger = logging.getLogger(__name__)
app = FastAPI(title="Corner — Approval API")

_pipeline_status: dict = {
    "running": False,
    "run_id": None,
    "stage": None,
    "started_at": None,
    "finished_at": None,
    "result": None,
    "errors": [],
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DRAFT_PATH = "/tmp/digest_draft.json"


def _get_db():
    return psycopg2.connect(settings.postgres_url)


def load_draft() -> dict:
    if not os.path.exists(DRAFT_PATH):
        raise HTTPException(status_code=404, detail="No draft pending")
    with open(DRAFT_PATH) as f:
        return json.load(f)


class ApprovalRequest(BaseModel):
    approved: bool
    edited_digest: Optional[str] = None


@app.get("/")
def health():
    return {"status": "ok", "service": "corner-approval"}


@app.get("/draft")
def get_draft():
    """Return the current pending digest for review."""
    draft = load_draft()
    return {
        "run_id":       draft["run_id"],
        "item_count":   draft["item_count"],
        "error_count":  draft["error_count"],
        "errors":       draft["errors"],
        "digest":       draft["digest_draft"],
    }


@app.post("/approve")
def approve_draft(req: ApprovalRequest):
    """
    Human approval gate.
    approved=true  → publishes to Slack (using edited_digest if provided)
    approved=false → rejects without publishing
    """
    draft = load_draft()

    if not req.approved:
        logger.info(f"Digest rejected for run {draft['run_id']}")
        os.remove(DRAFT_PATH)
        return {"status": "rejected", "run_id": draft["run_id"]}

    final_text = req.edited_digest or draft["digest_draft"]
    success = publish_to_slack(final_text)

    if success:
        save_published_digest(
            draft["run_id"], final_text, draft.get("item_count", 0)
        )
        os.remove(DRAFT_PATH)
        return {"status": "published", "run_id": draft["run_id"]}
    else:
        return {
            "status": "publish_failed",
            "detail": "Slack delivery failed — check SLACK_WEBHOOK_URL in .env"
        }


@app.post("/reject")
def reject_draft():
    """Convenience endpoint — reject without a request body."""
    draft = load_draft()
    os.remove(DRAFT_PATH)
    logger.info(f"Digest rejected for run {draft['run_id']}")
    return {"status": "rejected", "run_id": draft["run_id"]}


@app.get("/runs")
def list_runs(limit: int = Query(20, ge=1, le=100)):
    """Return recent pipeline runs from run_logs, grouped by run_id."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT run_id,
                       MIN(created_at) AS started_at,
                       MAX(created_at) AS ended_at,
                       ARRAY_AGG(DISTINCT stage) AS stages,
                       BOOL_OR(status = 'error') AS has_errors,
                       COUNT(*) FILTER (WHERE status = 'error') AS error_count
                FROM run_logs
                GROUP BY run_id
                ORDER BY MIN(created_at) DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            for row in rows:
                row["started_at"] = row["started_at"].isoformat() if row["started_at"] else None
                row["ended_at"] = row["ended_at"].isoformat() if row["ended_at"] else None
            return rows
    finally:
        conn.close()


@app.get("/scored-items")
def list_scored_items(
    limit: int = Query(50, ge=1, le=200),
    tier: Optional[str] = None,
    tag: Optional[str] = None,
):
    """Return scored items joined with their source info."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            where_clauses = []
            params: list = []

            if tier:
                where_clauses.append("si.source_tier = %s")
                params.append(tier)
            if tag:
                where_clauses.append("%s = ANY(sc.impact_tags)")
                params.append(tag)

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            cur.execute(f"""
                SELECT sc.id, si.title, si.source_name, si.source_tier,
                       si.canonical_url, si.published_at,
                       sc.relevance, sc.novelty, sc.urgency, sc.confidence,
                       sc.what_changed, sc.why_it_matters,
                       sc.recommended_action, sc.impact_tags,
                       sc.approved, sc.scored_at
                FROM scored_items sc
                JOIN source_items si ON sc.source_item_id = si.id
                {where_sql}
                ORDER BY sc.scored_at DESC
                LIMIT %s
            """, params + [limit])
            rows = cur.fetchall()
            for row in rows:
                for key in ("published_at", "scored_at"):
                    if row.get(key):
                        row[key] = row[key].isoformat()
            return rows
    finally:
        conn.close()


@app.get("/stats")
def get_stats():
    """Dashboard summary stats."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS total FROM source_items")
            total_sources = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(*) AS total FROM scored_items")
            total_scored = cur.fetchone()["total"]

            cur.execute("SELECT COUNT(DISTINCT run_id) AS total FROM run_logs")
            total_runs = cur.fetchone()["total"]

            cur.execute("""
                SELECT AVG(relevance) AS avg_relevance,
                       AVG(novelty) AS avg_novelty,
                       AVG(urgency) AS avg_urgency
                FROM scored_items
            """)
            averages = cur.fetchone()
            for k, v in averages.items():
                averages[k] = round(float(v), 3) if v else 0.0

            cur.execute("SELECT COUNT(*) AS total FROM published_digests")
            total_published = cur.fetchone()["total"]

            cur.execute("""
                SELECT run_id, MAX(created_at) AS ended_at,
                       SUM(item_count) FILTER (WHERE stage = 'score') AS scored_count
                FROM run_logs
                GROUP BY run_id
                ORDER BY MAX(created_at) DESC
                LIMIT 1
            """)
            last_run_row = cur.fetchone()
            last_run = None
            if last_run_row:
                last_run = {
                    "run_id": last_run_row["run_id"],
                    "ended_at": last_run_row["ended_at"].isoformat() if last_run_row["ended_at"] else None,
                    "scored_count": last_run_row["scored_count"] or 0,
                }

            # Count items scored in last 24h vs before
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE scored_at > NOW() - INTERVAL '24 hours') AS new_today,
                       COUNT(*) FILTER (WHERE scored_at <= NOW() - INTERVAL '24 hours') AS older
                FROM scored_items
            """)
            freshness = cur.fetchone()

            has_pending = os.path.exists(DRAFT_PATH)

            return {
                "total_sources": total_sources,
                "total_scored": total_scored,
                "total_runs": total_runs,
                "total_published": total_published,
                "averages": averages,
                "has_pending_draft": has_pending,
                "last_run": last_run,
                "new_today": freshness["new_today"],
                "older_items": freshness["older"],
            }
    finally:
        conn.close()


@app.get("/published")
def list_published(limit: int = Query(10, ge=1, le=50)):
    """Return recently published digests."""
    conn = _get_db()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, run_id, digest_text, item_count, published_at
                FROM published_digests
                ORDER BY published_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()
            for row in rows:
                if row.get("published_at"):
                    row["published_at"] = row["published_at"].isoformat()
            return rows
    finally:
        conn.close()


def _run_pipeline_thread():
    """Execute the pipeline in a background thread."""
    global _pipeline_status
    try:
        _pipeline_status["stage"] = "collect"
        from agent.pipeline.runner import run_pipeline
        final_state = run_pipeline()

        _pipeline_status["result"] = "success"
        _pipeline_status["errors"] = final_state.get("errors", [])
        _pipeline_status["stage"] = "done"
        logger.info(f"Pipeline thread finished: {final_state['run_id']}")
    except Exception as e:
        _pipeline_status["result"] = "error"
        _pipeline_status["errors"] = [str(e)]
        _pipeline_status["stage"] = "failed"
        logger.error(f"Pipeline thread failed: {e}")
    finally:
        _pipeline_status["running"] = False
        _pipeline_status["finished_at"] = datetime.now(timezone.utc).isoformat()


@app.post("/run-pipeline")
def trigger_pipeline():
    """Start the pipeline in a background thread."""
    global _pipeline_status

    if _pipeline_status["running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline already running (run_id: {_pipeline_status['run_id']})"
        )

    import uuid
    run_id = str(uuid.uuid4())

    _pipeline_status = {
        "running": True,
        "run_id": run_id,
        "stage": "starting",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result": None,
        "errors": [],
    }

    thread = threading.Thread(target=_run_pipeline_thread, daemon=True)
    thread.start()

    return {"status": "started", "run_id": run_id}


@app.get("/pipeline-status")
def get_pipeline_status():
    """Check if a pipeline run is in progress and its status."""
    return _pipeline_status