# agent/publishing/approval_api.py
import json
import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent.publishing.slack import publish_to_slack

logger = logging.getLogger(__name__)
app = FastAPI(title="Corner — Approval API")

DRAFT_PATH = "/tmp/digest_draft.json"


def load_draft() -> dict:
    if not os.path.exists(DRAFT_PATH):
        raise HTTPException(status_code=404, detail="No draft pending")
    with open(DRAFT_PATH) as f:
        return json.load(f)


class ApprovalRequest(BaseModel):
    approved: bool
    edited_digest: Optional[str] = None  # human can rewrite before publishing


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
        return {"status": "rejected", "run_id": draft["run_id"]}

    # Use the human-edited version if provided, otherwise use the original
    final_text = req.edited_digest or draft["digest_draft"]

    success = publish_to_slack(final_text)

    if success:
        # Remove draft so it is not accidentally published twice
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
    logger.info(f"Digest rejected for run {draft['run_id']}")
    return {"status": "rejected", "run_id": draft["run_id"]}