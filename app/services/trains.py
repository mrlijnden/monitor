import httpx
from datetime import datetime
from app.config import CACHE_TTL
from app.core.cache import cache

# Using the public OVapi for train departures (same as transit but filtered for trains)
OVAPI_URL = "http://v0.ovapi.nl/stopareacode"

# Amsterdam train stations
TRAIN_STATIONS = [
    ("AmsCS", "Amsterdam Centraal"),
    ("AmsZd", "Amsterdam Zuid"),
    ("AssSl", "Amsterdam Sloterdijk"),
]


async def fetch_trains() -> dict:
    """Fetch train departures from Amsterdam stations."""
    departures = []

    async with httpx.AsyncClient() as client:
        for station_code, station_name in TRAIN_STATIONS:
            try:
                url = f"{OVAPI_URL}/{station_code}"
                response = await client.get(url, timeout=10.0)

                if response.status_code != 200:
                    continue

                data = response.json()

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

                            # Filter for trains only (NS, Thalys, etc.)
                            transport_type = pass_data.get("TransportType", "")
                            if transport_type not in ["TRAIN", "TRAM"]:  # TRAM for metro
                                continue

                            expected = pass_data.get("ExpectedDepartureTime") or pass_data.get("ExpectedArrivalTime")
                            if not expected:
                                continue

                            try:
                                exp_time = datetime.fromisoformat(expected.replace("Z", "+00:00"))
                                now = datetime.now(exp_time.tzinfo)
                                minutes = int((exp_time - now).total_seconds() / 60)

                                if minutes < 0 or minutes > 90:
                                    continue

                                departures.append({
                                    "line": pass_data.get("LinePublicNumber", "?"),
                                    "destination": pass_data.get("DestinationName50", "Unknown"),
                                    "minutes": minutes,
                                    "station": station_name,
                                    "platform": pass_data.get("TimingPointName", ""),
                                    "operator": pass_data.get("DataOwnerCode", ""),
                                })
                            except Exception:
                                continue

            except Exception:
                continue

    # Sort by departure time
    departures.sort(key=lambda x: x["minutes"])

    result = {
        "departures": departures[:15],
        "updated_at": datetime.now().isoformat(),
    }

    cache.set("trains", result, CACHE_TTL.get("trains", 120))
    return result


async def get_trains() -> dict:
    """Get train departures from cache or fetch if needed."""
    cached = cache.get("trains")
    if cached:
        return cached
    return await fetch_trains()
