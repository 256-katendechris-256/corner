# agent/ingestion/rss.py
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from agent.ingestion.web import fetch_page
from agent.normalisation.schemas import SourceItem, SourceTier
import logging

logger = logging.getLogger(__name__)

# Tier 2 source registry
TIER2_SOURCES = [
    {
        'name': 'The Batch (DeepLearning.AI)',
        'rss': 'https://www.deeplearning.ai/the-batch/feed/',
    },
    {
        'name': 'Simon Willison Blog',
        'rss': 'https://simonwillison.net/atom/everything/',
    },
    {
        'name': 'Lenny Newsletter',
        'rss': 'https://www.lennysnewsletter.com/feed',
    },
    # Add more newsletters here as needed
]

def parse_date(entry) -> datetime:
    """Extract publication date from an RSS entry."""
    try:
        if hasattr(entry, 'published'):
            return parsedate_to_datetime(entry.published)
    except Exception:
        pass
    return datetime.now(timezone.utc)

def ingest_tier2(max_per_feed: int = 10) -> list[SourceItem]:
    """
    Fetch recent entries from all Tier 2 RSS feeds.
    For each entry, fetch the full article text via web fetcher.
    """
    items = []
    for source in TIER2_SOURCES:
        logger.info(f"Parsing RSS: {source['name']}")
        feed = feedparser.parse(source['rss'])

        if feed.bozo:  # feedparser sets bozo=True on parse errors
            logger.warning(f"Feed parse error: {feed.bozo_exception}")

        for entry in feed.entries[:max_per_feed]:
            url = entry.get('link', '')
            if not url:
                continue

            # Fetch full article text (not just the RSS excerpt)
            content = fetch_page(url)
            if content is None:
                content = entry.get('summary', '')  # fall back to excerpt

            item = SourceItem(
                id=SourceItem.make_id(source['name'], url),
                title=entry.get('title', 'Untitled'),
                source_name=source['name'],
                source_tier=SourceTier.TIER2,
                published_at=parse_date(entry),
                canonical_url=url,
                raw_content=content or '',
            )
            items.append(item)

    logger.info(f'Tier 2: {len(items)} items ingested')
    return items

"""
max_per_feed=10 limits you to the 10 most recent articles per feed. On the first run you may want to
increase this to 50 to back-fill history. On subsequent daily runs, 5-10 is sufficient.

"""