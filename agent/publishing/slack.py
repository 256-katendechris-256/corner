# agent/publishing/slack.py
import logging
from agent.config import settings

logger = logging.getLogger(__name__)


def _markdown_to_slack(text: str) -> str:
    """
    Convert standard markdown to Slack mrkdwn format.
    Slack uses *bold* not **bold**, and has no headers.
    """
    import re
    # **bold** → *bold*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    # ### Heading → *Heading* with a divider feel
    text = re.sub(r'^### (.+)$', r'\n*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$',  r'\n*\1*', text, flags=re.MULTILINE)
    return text


def build_slack_blocks(text: str) -> list:
    """
    Convert digest text into Slack Block Kit blocks.
    Each item becomes a clean section with a divider.
    """
    blocks = []
    sections = text.strip().split('\n\n')

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Convert markdown to Slack mrkdwn
        slack_text = _markdown_to_slack(section)

        # Slack section blocks have a 3000 char limit
        if len(slack_text) > 2900:
            slack_text = slack_text[:2900] + "..."

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": slack_text}
        })
        blocks.append({"type": "divider"})

    return blocks


def publish_to_slack(text: str | None) -> bool:
    if not text:
        logger.warning("publish_to_slack called with empty text — skipping")
        return False

    if not settings.slack_webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping")
        return False

    from slack_sdk.webhook import WebhookClient
    client = WebhookClient(settings.slack_webhook_url)

    # Build Block Kit blocks for clean formatting
    blocks = build_slack_blocks(text)

    # Slack allows max 50 blocks per message — chunk if needed
    chunk_size = 48  # leave room for header/footer blocks
    block_chunks = [
        blocks[i:i+chunk_size]
        for i in range(0, len(blocks), chunk_size)
    ]

    for i, chunk in enumerate(block_chunks):
        # Add a header block on the first chunk
        if i == 0:
            header = [{
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "AI Market Intelligence — Daily Digest"
                }
            }]
            chunk = header + chunk

        response = client.send(
            text="AI Market Intelligence Digest",  # fallback for notifications
            blocks=chunk
        )
        if response.status_code != 200:
            logger.error(f"Slack error {response.status_code}: {response.body}")
            return False

    logger.info(f"Published to Slack ({len(block_chunks)} message(s))")
    return True