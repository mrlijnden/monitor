import httpx
from datetime import datetime, timedelta
from app.config import TICKETMASTER_URL, TICKETMASTER_API_KEY, CACHE_TTL
from app.core.cache import cache


async def fetch_events() -> dict:
    """Fetch events from Ticketmaster API."""
    events = []

    if not TICKETMASTER_API_KEY:
        # Return sample data if no API key
        return {
            "events": [
                {"name": "Configure TICKETMASTER_API_KEY for events", "date": "", "venue": "", "category": "info"}
            ],
            "updated_at": datetime.now().isoformat(),
        }

    try:
        now = datetime.utcnow()
        end = now + timedelta(days=14)

        params = {
            "city": "Amsterdam",
            "countryCode": "NL",
            "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "size": 15,
            "apikey": TICKETMASTER_API_KEY,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(TICKETMASTER_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            embedded = data.get("_embedded", {})
            for event in embedded.get("events", []):
                venue_name = ""
                venues = event.get("_embedded", {}).get("venues", [])
                if venues:
                    venue_name = venues[0].get("name", "")

                date_info = event.get("dates", {}).get("start", {})
                event_date = date_info.get("localDate", "")
                event_time = date_info.get("localTime", "")

                classifications = event.get("classifications", [])
                category = ""
                if classifications:
                    category = classifications[0].get("segment", {}).get("name", "")

                events.append({
                    "name": event.get("name", "Unknown Event"),
                    "date": f"{event_date} {event_time}".strip(),
                    "venue": venue_name,
                    "category": category,
                    "url": event.get("url", ""),
                })

    except Exception as e:
        cached = cache.get("events")
        if cached:
            return cached
        return {"events": [], "error": str(e), "updated_at": datetime.now().isoformat()}

    result = {
        "events": events,
        "updated_at": datetime.now().isoformat(),
    }

    cache.set("events", result, CACHE_TTL["events"])
    return result


async def get_events() -> dict:
    """Get events from cache or fetch if needed."""
    cached = cache.get("events")
    if cached:
        return cached
    return await fetch_events()
