# agent/publishing/approval_api.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import json, os

app = FastAPI(title='Market Intel Approval')

# In production: store drafts in Postgres, not a file
DRAFT_PATH = '/tmp/digest_draft.json'

class ApprovalRequest(BaseModel):
    approved: bool
    edited_digest: Optional[str] = None  # human-edited version

@app.get('/draft')
def get_draft():
    """Return the current pending digest draft."""
    if not os.path.exists(DRAFT_PATH):
        return {'status': 'no draft pending'}
    with open(DRAFT_PATH) as f:
        return json.load(f)

@app.post('/approve')
def approve_draft(req: ApprovalRequest):
    """Human approves (or rejects) the digest."""
    if not req.approved:
        return {'status': 'rejected'}

    with open(DRAFT_PATH) as f:
        draft = json.load(f)

    final_text = req.edited_digest or draft['digest_draft']
    publish_to_slack(final_text)
    return {'status': 'published'}

def publish_to_slack(text: str) -> None:
    from slack_sdk.webhook import WebhookClient
    from agent.config import settings
    client = WebhookClient(settings.slack_webhook_url)
    client.send(text=text)

# Start with:
# uvicorn agent.publishing.approval_api:app --reload --port 8000