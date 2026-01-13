import httpx
from datetime import datetime
from app.config import OVAPI_URL, CACHE_TTL, amsterdam_now
from app.core.cache import cache

# Key Amsterdam stop areas - Major transit hubs and popular stops
# Using known OVapi stop area codes
AMSTERDAM_STOPS = [
    # Major hubs (confirmed working)
    "AmsCS",      # Amsterdam Centraal Station
    "AmsDam",     # Dam
    "AmsLei",     # Leidseplein
    "AmsZd",      # Amsterdam Zuid (WTC)
    "AssSl",      # Amsterdam Sloterdijk
    "AmsAm",      # Amstelstation
    
    # Additional major stops (will try these)
    "AmsNie",     # Nieuwmarkt
    "AmsWib",     # Wibautstraat
    "AmsMu",      # Museumplein
    "AmsVij",     # Vijzelgracht
    "AmsWes",     # Westermarkt
    "AmsBij",     # Bijlmer Arena
]


async def fetch_transit() -> dict:
    """Fetch real-time transit data from OVapi for Amsterdam stops."""
    departures = []
    successful_stops = []

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
                                now = amsterdam_now().astimezone(exp_time.tzinfo)
                                minutes = int((exp_time - now).total_seconds() / 60)

                                if minutes < 0 or minutes > 60:
                                    continue

                                transport_type = pass_data.get("TransportType", "BUS")
                                
                                # Map transport types to readable names and emojis
                                type_map = {
                                    "BUS": ("Bus", "🚌"),
                                    "TRAM": ("Tram", "🚊"),
                                    "METRO": ("Metro", "🚇"),
                                    "FERRY": ("Veer", "⛴️"),
                                    "TRAIN": ("Trein", "🚆")
                                }
                                transport_info = type_map.get(transport_type, (transport_type, "🚍"))
                                transport_name, transport_emoji = transport_info
                                
                                departures.append({
                                    "line": pass_data.get("LinePublicNumber", "?"),
                                    "destination": pass_data.get("DestinationName50", "Unknown"),
                                    "minutes": minutes,
                                    "stop": pass_data.get("TimingPointName", stop_code),
                                    "transport_type": transport_type,
                                    "transport_name": transport_name,
                                    "transport_emoji": transport_emoji,
                                    "operator": pass_data.get("DataOwnerCode", ""),
                                })
                            except Exception:
                                continue
                    
                    # Mark this stop as successful if we got data
                    if any(dep.get("stop") == stop_code or stop_code in str(dep.get("stop", "")) for dep in departures[-10:]):
                        successful_stops.append(stop_code)

            except Exception as e:
                print(f"Error fetching stop {stop_code}: {e}")
                continue

    # Sort by departure time
    departures.sort(key=lambda x: x["minutes"])

    # Remove duplicates (same line, destination, time)
    seen = set()
    unique_departures = []
    for dep in departures:
        key = (dep["line"], dep["destination"], dep["minutes"], dep["stop"])
        if key not in seen:
            seen.add(key)
            unique_departures.append(dep)
    
    result = {
        "departures": unique_departures[:30],  # Show more departures
        "updated_at": amsterdam_now().isoformat(),
        "stops_checked": len(AMSTERDAM_STOPS),
        "stops_with_data": len(successful_stops),
    }

    cache.set("transit", result, CACHE_TTL["transit"])
    return result


async def get_transit() -> dict:
    """Get transit data from cache or fetch if needed."""
    cached = cache.get("transit")
    if cached:
        return cached
    return await fetch_transit()
