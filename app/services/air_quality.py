import httpx
from datetime import datetime
from app.config import AMSTERDAM_LAT, AMSTERDAM_LON, CACHE_TTL, amsterdam_now
from app.core.cache import cache

# Open-Meteo Air Quality API (FREE, no key required)
OPEN_METEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# European AQI levels
AQI_LEVELS = [
    (20, "Good", "green"),
    (40, "Fair", "yellow"),
    (60, "Moderate", "orange"),
    (80, "Poor", "red"),
    (100, "Very Poor", "purple"),
    (999, "Extremely Poor", "maroon"),
]


def get_aqi_level(aqi: int) -> tuple[str, str]:
    """Get European AQI level description and color."""
    for threshold, level, color in AQI_LEVELS:
        if aqi <= threshold:
            return level, color
    return "Extremely Poor", "maroon"


async def fetch_air_quality() -> dict:
    """Fetch air quality data from Open-Meteo API (FREE, no key)."""
    try:
        params = {
            "latitude": AMSTERDAM_LAT,
            "longitude": AMSTERDAM_LON,
            "current": "european_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
            "timezone": "Europe/Amsterdam",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(OPEN_METEO_AQ_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})
            aqi = current.get("european_aqi", 0)
            level, color = get_aqi_level(aqi)

            pollutants = {}
            pollutant_map = {
                "pm2_5": "PM2.5",
                "pm10": "PM10",
                "nitrogen_dioxide": "NO2",
                "sulphur_dioxide": "SO2",
                "carbon_monoxide": "CO",
                "ozone": "O3",
            }

            for key, label in pollutant_map.items():
                value = current.get(key)
                if value is not None:
                    pollutants[label] = round(value, 1)

            result = {
                "aqi": aqi,
                "level": level,
                "color": color,
                "pollutants": pollutants,
                "station": "Amsterdam (Open-Meteo)",
                "updated_at": amsterdam_now().isoformat(),
            }

            cache.set("air_quality", result, CACHE_TTL["air_quality"])
            return result

    except Exception as e:
        cached = cache.get("air_quality")
        if cached:
            return cached
        return {
            "aqi": None,
            "level": "Error",
            "color": "gray",
            "pollutants": {},
            "error": str(e),
            "updated_at": datetime.now().isoformat(),
        }


async def get_air_quality() -> dict:
    """Get air quality from cache or fetch if needed."""
    cached = cache.get("air_quality")
    if cached:
        return cached
    return await fetch_air_quality()
