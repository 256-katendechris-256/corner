# agent/ingestion/web.py
import httpx
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language":  "en-US,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate, br, zstd",
    "DNT":              "1",
    "Connection":       "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":   "document",
    "Sec-Fetch-Mode":   "navigate",
    "Sec-Fetch-Site":   "none",
    "Sec-Fetch-User":   "?1",
    "Sec-CH-UA":        '"Chromium";v="131", "Google Chrome";v="131", "Not?A_Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Linux"',
    "Cache-Control":    "max-age=0",
}


def _firecrawl_fetch(url: str, max_chars: int = 12000) -> str | None:
    """
    Fallback fetcher using Firecrawl for Cloudflare-protected pages.
    Only called when httpx gets a 403. Returns markdown text or None.
    """
    from agent.config import settings
    if not settings.firecrawl_api_key:
        logger.warning("  FIRECRAWL_API_KEY not set — cannot bypass 403")
        return None

    try:
        from firecrawl import FirecrawlApp
        app = FirecrawlApp(api_key=settings.firecrawl_api_key)
        doc = app.scrape(url, formats=["markdown"])
        if doc.markdown:
            logger.info(f"  Firecrawl OK — {len(doc.markdown)} chars from {url}")
            return doc.markdown[:max_chars]
        return None
    except Exception as e:
        logger.error(f"  Firecrawl failed for {url}: {e}")
        return None


def fetch_page(url: str, timeout: int = 20) -> str | None:
    """
    Fetch a URL and return clean plain text.
    1. Try httpx (free, fast — works for ~95% of sites)
    2. On 403, fall back to Firecrawl (handles Cloudflare)
    """
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout,
                          follow_redirects=True, http2=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return extract_text(resp.text)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            logger.info(f"  403 from httpx, trying Firecrawl: {url}")
            return _firecrawl_fetch(url)
        logger.error(f"HTTP {e.response.status_code} fetching {url}")
        return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


def extract_text(html: str, max_chars: int = 12000) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["nav","header","footer","script",
                     "style","aside","form"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]
