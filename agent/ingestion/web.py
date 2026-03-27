# agent/ingestion/web.py
import httpx
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

# Full browser-like headers — Cloudflare checks several of these
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language":  "en-US,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate, br",
    "DNT":              "1",
    "Connection":       "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":   "document",
    "Sec-Fetch-Mode":   "navigate",
    "Sec-Fetch-Site":   "none",
    "Sec-Fetch-User":   "?1",
    "Cache-Control":    "max-age=0",
}

def fetch_page(url: str, timeout: int = 20) -> str | None:
    """
    Fetch a URL and return clean plain text.
    Uses full browser headers to pass Cloudflare and similar bot detection.
    Returns None on any error.
    """
    try:
        with httpx.Client(headers=HEADERS, timeout=timeout,
                          follow_redirects=True, http2=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return extract_text(resp.text)
    except httpx.HTTPStatusError as e:
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