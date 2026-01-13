import httpx
from datetime import datetime
from app.config import AMSTERDAM_LAT, AMSTERDAM_LON, CACHE_TTL
from app.core.cache import cache

# Using weather data to provide cycling conditions
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def get_cycling_score(temp: float, wind: float, precip: float, humidity: float) -> tuple[int, str, str]:
    """Calculate cycling score based on weather conditions."""
    score = 100

    # Temperature penalty (ideal: 15-22°C)
    if temp < 5:
        score -= 30
    elif temp < 10:
        score -= 15
    elif temp > 28:
        score -= 20
    elif temp > 25:
        score -= 10

    # Wind penalty (ideal: < 15 km/h)
    if wind > 40:
        score -= 40
    elif wind > 30:
        score -= 25
    elif wind > 20:
        score -= 15
    elif wind > 15:
        score -= 5

    # Rain penalty
    if precip > 5:
        score -= 50
    elif precip > 2:
        score -= 30
    elif precip > 0.5:
        score -= 15
    elif precip > 0:
        score -= 5

    # Humidity penalty (high humidity + warm = uncomfortable)
    if humidity > 90:
        score -= 10
    elif humidity > 80 and temp > 20:
        score -= 5

    score = max(0, min(100, score))

    if score >= 80:
        return score, "Excellent", "green"
    elif score >= 60:
        return score, "Good", "yellow"
    elif score >= 40:
        return score, "Fair", "orange"
    else:
        return score, "Poor", "red"


async def fetch_bikes() -> dict:
    """Fetch cycling conditions for Amsterdam."""
    try:
        params = {
            "latitude": AMSTERDAM_LAT,
            "longitude": AMSTERDAM_LON,
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,weather_code",
            "hourly": "temperature_2m,precipitation_probability,wind_speed_10m",
            "timezone": "Europe/Amsterdam",
            "forecast_hours": 12,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(OPEN_METEO_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})
            hourly = data.get("hourly", {})

            temp = current.get("temperature_2m", 15)
            humidity = current.get("relative_humidity_2m", 50)
            precip = current.get("precipitation", 0)
            wind = current.get("wind_speed_10m", 10)

            score, condition, color = get_cycling_score(temp, wind, precip, humidity)

            # Build hourly forecast
            forecast = []
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            winds = hourly.get("wind_speed_10m", [])
            rain_probs = hourly.get("precipitation_probability", [])

            for i in range(min(6, len(times))):
                hour = times[i][11:16] if len(times[i]) > 11 else times[i]
                forecast.append({
                    "time": hour,
                    "temp": temps[i] if i < len(temps) else None,
                    "wind": winds[i] if i < len(winds) else None,
                    "rain_prob": rain_probs[i] if i < len(rain_probs) else None,
                })

            result = {
                "score": score,
                "condition": condition,
                "color": color,
                "current": {
                    "temperature": temp,
                    "humidity": humidity,
                    "precipitation": precip,
                    "wind_speed": wind,
                },
                "forecast": forecast,
                "tip": get_cycling_tip(score, temp, wind, precip),
                "updated_at": datetime.now().isoformat(),
            }

            cache.set("bikes", result, CACHE_TTL.get("bikes", 900))
            return result

    except Exception as e:
        cached = cache.get("bikes")
        if cached:
            return cached
        return {
            "score": None,
            "condition": "Error",
            "color": "gray",
            "current": {},
            "forecast": [],
            "tip": "",
            "error": str(e),
            "updated_at": datetime.now().isoformat(),
        }


def get_cycling_tip(score: int, temp: float, wind: float, precip: float) -> str:
    """Get a cycling tip based on conditions."""
    if precip > 2:
        return "Rain gear essential"
    elif precip > 0:
        return "Light rain possible"
    elif wind > 30:
        return "Strong headwinds likely"
    elif wind > 20:
        return "Moderate wind, plan route"
    elif temp < 5:
        return "Dress warmly, gloves recommended"
    elif temp > 28:
        return "Stay hydrated"
    elif score >= 80:
        return "Perfect cycling weather!"
    elif score >= 60:
        return "Good conditions for cycling"
    else:
        return "Consider alternatives"


async def get_bikes() -> dict:
    """Get cycling conditions from cache or fetch if needed."""
    cached = cache.get("bikes")
    if cached:
        return cached
    return await fetch_bikes()
