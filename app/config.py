import os
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Amsterdam timezone
AMSTERDAM_TZ = ZoneInfo("Europe/Amsterdam")


def amsterdam_now() -> datetime:
    """Get current datetime in Amsterdam timezone."""
    return datetime.now(AMSTERDAM_TZ)

# Amsterdam coordinates
AMSTERDAM_LAT = 52.3676
AMSTERDAM_LON = 4.9041

# API Keys (optional - most work without)
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")

# API Endpoints
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
OVAPI_URL = "http://v0.ovapi.nl/stopareacode"

# RSS Feeds for Dutch news
NEWS_FEEDS = [
    "https://feeds.nos.nl/nosnieuwsalgemeen",
    "https://www.dutchnews.nl/feed/",
]

# Refresh intervals in seconds
REFRESH_INTERVALS = {
    "weather": 1800,      # 30 minutes
    "news": 600,          # 10 minutes
    "hackernews": 600,    # 10 minutes
    "transit": 60,        # 1 minute
    "trains": 120,        # 2 minutes
    "events": 3600,       # 1 hour
    "air_quality": 900,   # 15 minutes
    "markets": 120,       # 2 minutes
    "parking": 300,       # 5 minutes
    "bikes": 900,         # 15 minutes
    "flights": 120,       # 2 minutes
}

# Cache TTL (slightly longer than refresh to handle delays)
CACHE_TTL = {
    "weather": 2000,
    "news": 700,
    "hackernews": 700,
    "transit": 90,
    "trains": 150,
    "events": 4000,
    "air_quality": 1000,
    "markets": 150,
    "parking": 350,
    "bikes": 1000,
    "flights": 150,
}
