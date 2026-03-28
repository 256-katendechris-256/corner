# agent/publishing/slack.py
import logging
from agent.config import settings

logger = logging.getLogger(__name__)


def publish_to_slack(text: str) -> bool:
    """
    Send text to the configured Slack webhook.
    Returns True on success, False on failure.
    Slack has a 3000 character limit per block — we chunk if needed.
    """
    if not settings.slack_webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack publish")
        return False

    from slack_sdk.webhook import WebhookClient
    client = WebhookClient(settings.slack_webhook_url)

    # Slack's text field limit is 3000 chars per message
    chunks = [text[i:i+2900] for i in range(0, len(text), 2900)]

    for i, chunk in enumerate(chunks):
        prefix = f"_(part {i+1}/{len(chunks)})_\n" if len(chunks) > 1 else ""
        response = client.send(text=prefix + chunk)
        if response.status_code != 200:
            logger.error(f"Slack error: {response.status_code} — {response.body}")
            return False

    logger.info(f"Published to Slack ({len(chunks)} message(s))")
    return True