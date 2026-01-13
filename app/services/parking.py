import httpx
from datetime import datetime
from app.config import CACHE_TTL, amsterdam_now
from app.core.cache import cache

# Note: The original Amsterdam parking API (opd.it-t.nl) is deprecated.
# Using sample data for demonstration. Replace with active API when available.

SAMPLE_GARAGES = [
    {"name": "P+R Amsterdam Noord", "capacity": 1200, "free_spaces": 450, "state": "ok"},
    {"name": "P+R Sloterdijk", "capacity": 800, "free_spaces": 312, "state": "ok"},
    {"name": "P+R RAI", "capacity": 600, "free_spaces": 89, "state": "ok"},
    {"name": "Parking Centrum", "capacity": 400, "free_spaces": 23, "state": "ok"},
    {"name": "P+R Zeeburg", "capacity": 500, "free_spaces": 234, "state": "ok"},
    {"name": "Europarking", "capacity": 350, "free_spaces": 67, "state": "ok"},
    {"name": "P+R Bijlmer Arena", "capacity": 700, "free_spaces": 445, "state": "ok"},
    {"name": "Muziekgebouw", "capacity": 200, "free_spaces": 12, "state": "ok"},
    {"name": "P+R Olympisch Stadion", "capacity": 450, "free_spaces": 178, "state": "ok"},
    {"name": "De Kolk", "capacity": 300, "free_spaces": 56, "state": "ok"},
]


async def fetch_parking() -> dict:
    """Fetch Amsterdam parking garage availability."""
    garages = []

    # Use sample data (real API is deprecated)
    for garage in SAMPLE_GARAGES:
        capacity = garage["capacity"]
        free_spaces = garage["free_spaces"]

        # Simulate some variation
        import random
        variation = random.randint(-20, 20)
        free_spaces = max(0, min(capacity, free_spaces + variation))

        occupancy = int((1 - free_spaces / capacity) * 100) if capacity > 0 else 0

        garages.append({
            "name": garage["name"],
            "free_spaces": free_spaces,
            "capacity": capacity,
            "occupancy": occupancy,
            "state": garage["state"],
        })

    # Sort by free spaces (most available first)
    garages.sort(key=lambda x: x["free_spaces"], reverse=True)

    result = {
        "garages": garages[:12],
        "source": "sample",  # Indicates using sample data
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
