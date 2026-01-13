import httpx
from app.config import OPEN_METEO_URL, AMSTERDAM_LAT, AMSTERDAM_LON, CACHE_TTL
from app.core.cache import cache

WEATHER_CODES = {
    0: ("Clear sky", "clear"),
    1: ("Mainly clear", "clear"),
    2: ("Partly cloudy", "cloudy"),
    3: ("Overcast", "cloudy"),
    45: ("Foggy", "fog"),
    48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "rain"),
    53: ("Moderate drizzle", "rain"),
    55: ("Dense drizzle", "rain"),
    61: ("Slight rain", "rain"),
    63: ("Moderate rain", "rain"),
    65: ("Heavy rain", "rain"),
    71: ("Slight snow", "snow"),
    73: ("Moderate snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Slight rain showers", "rain"),
    81: ("Moderate rain showers", "rain"),
    82: ("Violent rain showers", "rain"),
    85: ("Slight snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "storm"),
    96: ("Thunderstorm with hail", "storm"),
    99: ("Thunderstorm with heavy hail", "storm"),
}


async def fetch_weather() -> dict:
    """Fetch weather data from Open-Meteo API."""
    params = {
        "latitude": AMSTERDAM_LAT,
        "longitude": AMSTERDAM_LON,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
        "timezone": "Europe/Amsterdam",
        "forecast_days": 5,
        "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(OPEN_METEO_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})
            daily = data.get("daily", {})

            weather_code = current.get("weather_code", 0)
            description, icon = WEATHER_CODES.get(weather_code, ("Unknown", "unknown"))

            result = {
                "current": {
                    "temperature": current.get("temperature_2m"),
                    "humidity": current.get("relative_humidity_2m"),
                    "wind_speed": current.get("wind_speed_10m"),
                    "weather_code": weather_code,
                    "description": description,
                    "icon": icon,
                },
                "forecast": [],
            }

            # Build 5-day forecast
            if daily.get("time"):
                for i in range(min(5, len(daily["time"]))):
                    code = daily.get("weather_code", [0])[i] if daily.get("weather_code") else 0
                    desc, ic = WEATHER_CODES.get(code, ("Unknown", "unknown"))
                    result["forecast"].append({
                        "date": daily["time"][i],
                        "temp_max": daily.get("temperature_2m_max", [None])[i],
                        "temp_min": daily.get("temperature_2m_min", [None])[i],
                        "precipitation": daily.get("precipitation_sum", [0])[i],
                        "description": desc,
                        "icon": ic,
                    })

            cache.set("weather", result, CACHE_TTL["weather"])
            return result

    except Exception as e:
        cached = cache.get("weather")
        if cached:
            return cached
        return {"error": str(e), "current": None, "forecast": []}


async def get_weather() -> dict:
    """Get weather data from cache or fetch if needed."""
    cached = cache.get("weather")
    if cached:
        return cached
    return await fetch_weather()
