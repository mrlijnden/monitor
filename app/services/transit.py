import httpx
from datetime import datetime
from app.config import OVAPI_URL, CACHE_TTL
from app.core.cache import cache

# Key Amsterdam stop areas
AMSTERDAM_STOPS = [
    "AmsCS",      # Amsterdam Centraal
    "AmsDam",     # Dam
    "AmsLei",     # Leidseplein
]


async def fetch_transit() -> dict:
    """Fetch real-time transit data from OVapi."""
    departures = []

    async with httpx.AsyncClient() as client:
        for stop_code in AMSTERDAM_STOPS:
            try:
                url = f"{OVAPI_URL}/{stop_code}"
                response = await client.get(url, timeout=10.0)

                if response.status_code != 200:
                    continue

                data = response.json()

                # OVapi returns nested structure
                for stop_area_code, stop_area_data in data.items():
                    if not isinstance(stop_area_data, dict):
                        continue

                    for timing_point, tp_data in stop_area_data.items():
                        if not isinstance(tp_data, dict):
                            continue

                        passes = tp_data.get("Passes", {})
                        if not isinstance(passes, dict):
                            continue

                        for pass_id, pass_data in passes.items():
                            if not isinstance(pass_data, dict):
                                continue

                            # Calculate minutes until departure
                            expected = pass_data.get("ExpectedDepartureTime") or pass_data.get("ExpectedArrivalTime")
                            if not expected:
                                continue

                            try:
                                exp_time = datetime.fromisoformat(expected.replace("Z", "+00:00"))
                                now = datetime.now(exp_time.tzinfo)
                                minutes = int((exp_time - now).total_seconds() / 60)

                                if minutes < 0 or minutes > 60:
                                    continue

                                departures.append({
                                    "line": pass_data.get("LinePublicNumber", "?"),
                                    "destination": pass_data.get("DestinationName50", "Unknown"),
                                    "minutes": minutes,
                                    "stop": pass_data.get("TimingPointName", stop_code),
                                    "transport_type": pass_data.get("TransportType", "BUS"),
                                })
                            except Exception:
                                continue

            except Exception:
                continue

    # Sort by departure time
    departures.sort(key=lambda x: x["minutes"])

    result = {
        "departures": departures[:20],
        "updated_at": datetime.now().isoformat(),
    }

    cache.set("transit", result, CACHE_TTL["transit"])
    return result


async def get_transit() -> dict:
    """Get transit data from cache or fetch if needed."""
    cached = cache.get("transit")
    if cached:
        return cached
    return await fetch_transit()
