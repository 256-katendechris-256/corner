# agent/ingestion/tier1.py
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from agent.ingestion.web import fetch_page
from agent.normalisation.schemas import SourceItem, SourceTier
import logging

logger = logging.getLogger(__name__)

# ── Tier 1: scraped pages ────────────────────────────────────────────────────
TIER1_PAGES = [
    {
        "name": "OpenAI API Changelog",
        "url":  "https://platform.openai.com/docs/changelog",
    },
    {
        "name": "OpenAI Deprecations",
        "url":  "https://platform.openai.com/docs/deprecations",
    },
    {
        "name": "ChatGPT Release Notes",
        "url":  "https://help.openai.com/en/articles/6825453-chatgpt-release-notes",
    },
    {
        "name": "Anthropic Release Notes",
        "url":  "https://docs.anthropic.com/en/release-notes/overview",
    },
]

# ── Tier 1: RSS feeds (more reliable than scraping) ─────────────────────────
# NOTE: These are official or semi-official feeds that give structured data.
# OpenAI does not publish an API changelog RSS, so we use their news feed
# and developer forum as the closest signal. When a model ships, it appears
# in both the news feed and the forum before the changelog page updates.
TIER1_RSS = [
    {
        "name": "OpenAI News",
        "rss":  "https://openai.com/news/rss.xml",
    },
    {
        "name": "OpenAI Developer Forum",
        "rss":  "https://community.openai.com/latest.rss",
    },
    {
    "name": "Anthropic News",
    "rss":  "https://www.anthropic.com/rss.xml", 
    },

]

def _parse_date(entry) -> datetime:
    try:
        if hasattr(entry, "published"):
            return parsedate_to_datetime(entry.published)
    except Exception:
        pass
    return datetime.now(timezone.utc)

def ingest_tier1() -> list[SourceItem]:
    """
    Fetch all Tier 1 sources: scraped pages + RSS feeds.
    Scraped pages are attempted first; RSS feeds always run regardless.
    This means a 403 on a scraped page does not leave you with no signal.
    """
    items = []

    # ── Scraped pages ────────────────────────────────────────────────────────
    for source in TIER1_PAGES:
        logger.info(f"Fetching page: {source['name']}")
        content = fetch_page(source["url"])
        if content is None:
            logger.warning(f"  FAILED (will rely on RSS fallback): {source['name']}")
            continue
        items.append(SourceItem(
            id=SourceItem.make_id(source["name"], source["url"]),
            title=source["name"],
            source_name=source["name"],
            source_tier=SourceTier.TIER1,
            published_at=datetime.now(timezone.utc),
            canonical_url=source["url"],
            raw_content=content,
        ))
        logger.info(f"  OK — {len(content)} chars")

    # ── RSS feeds (always run) ───────────────────────────────────────────────
    for source in TIER1_RSS:
        logger.info(f"Parsing RSS: {source['name']}")
        feed = feedparser.parse(source["rss"])
        count = 0
        for entry in feed.entries[:15]:
            url = entry.get("link", "")
            if not url:
                continue
            content = (
                entry.get("summary", "")
                or entry.get("content", [{}])[0].get("value", "")
            )
            items.append(SourceItem(
                id=SourceItem.make_id(source["name"], url),
                title=entry.get("title", "Untitled"),
                source_name=source["name"],
                source_tier=SourceTier.TIER1,
                published_at=_parse_date(entry),
                canonical_url=url,
                raw_content=content[:12000],
            ))
            count += 1
        logger.info(f"  {count} entries from RSS")

    logger.info(f"Tier 1 total: {len(items)} items")
    return items