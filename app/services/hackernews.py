import httpx
from datetime import datetime
from app.config import CACHE_TTL, amsterdam_now
from app.core.cache import cache

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"


async def fetch_story(story_id: int) -> dict | None:
    """Fetch a single story by ID."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{HN_API_BASE}/item/{story_id}.json", timeout=5.0)
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return None


async def fetch_hackernews() -> dict:
    """Fetch top stories from Hacker News."""
    stories = []

    try:
        async with httpx.AsyncClient() as client:
            # Get top story IDs
            response = await client.get(f"{HN_API_BASE}/topstories.json", timeout=10.0)
            response.raise_for_status()
            story_ids = response.json()[:20]  # Top 20 stories

            # Fetch each story
            for story_id in story_ids[:15]:
                story = await fetch_story(story_id)
                if story and story.get("title"):
                    stories.append({
                        "title": story.get("title", ""),
                        "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                        "score": story.get("score", 0),
                        "comments": story.get("descendants", 0),
                        "by": story.get("by", ""),
                        "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
                    })

    except Exception as e:
        cached = cache.get("hackernews")
        if cached:
            return cached
        return {"stories": [], "error": str(e), "updated_at": datetime.now().isoformat()}

    result = {
        "stories": stories,
        "updated_at": amsterdam_now().isoformat(),
    }

    cache.set("hackernews", result, CACHE_TTL.get("hackernews", 600))
    return result


async def get_hackernews() -> dict:
    """Get Hacker News from cache or fetch if needed."""
    cached = cache.get("hackernews")
    if cached:
        return cached
    return await fetch_hackernews()
