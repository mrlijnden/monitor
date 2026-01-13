import feedparser
import httpx
from datetime import datetime
from app.config import NEWS_FEEDS, CACHE_TTL, amsterdam_now
from app.core.cache import cache


async def fetch_news() -> dict:
    """Fetch news from RSS feeds."""
    all_articles = []

    async with httpx.AsyncClient() as client:
        for feed_url in NEWS_FEEDS:
            try:
                response = await client.get(feed_url, timeout=10.0)
                feed = feedparser.parse(response.text)

                for entry in feed.entries[:10]:
                    published = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        published = datetime(*entry.published_parsed[:6]).isoformat()

                    all_articles.append({
                        "title": entry.get("title", "No title"),
                        "link": entry.get("link", ""),
                        "published": published,
                        "source": feed.feed.get("title", "Unknown"),
                    })
            except Exception:
                continue

    # Sort by published date (newest first)
    all_articles.sort(
        key=lambda x: x["published"] or "0000",
        reverse=True
    )

    result = {
        "articles": all_articles[:15],
        "updated_at": amsterdam_now().isoformat(),
    }

    cache.set("news", result, CACHE_TTL["news"])
    return result


async def get_news() -> dict:
    """Get news from cache or fetch if needed."""
    cached = cache.get("news")
    if cached:
        return cached
    return await fetch_news()
