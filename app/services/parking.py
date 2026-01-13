import httpx
from datetime import datetime
from app.config import CACHE_TTL, amsterdam_now
from app.core.cache import cache

# Note: The original Amsterdam parking API (opd.it-t.nl) is deprecated.
# TODO: Find alternative API or implement real-time parking data source

async def fetch_parking() -> dict:
    """Fetch Amsterdam parking garage availability."""
    # TODO: Implement real parking API
    # Return empty if no real data available
    result = {
        "garages": [],
        "source": None,
        "updated_at": amsterdam_now().isoformat(),
    }

    cache.set("parking", result, CACHE_TTL.get("parking", 300))
    return result


async def get_parking() -> dict:
    """Get parking data from cache or fetch if needed."""
    cached = cache.get("parking")
    if cached:
        return cached
    return await fetch_parking()
