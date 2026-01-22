"""FlightRadar24 live flight tracking service"""
import asyncio
from typing import Dict, List, Any
from datetime import datetime
from FlightRadar24 import FlightRadar24API

# Netherlands bounds (covers entire country)
# North: 53.55, South: 50.75, West: 3.35, East: 7.25
NL_BOUNDS = "53.55,50.75,3.35,7.25"

# Cache
_cache: Dict[str, Any] = {
    "flights": [],
    "updated": None
}

fr_api = FlightRadar24API()


def fetch_flights_sync() -> List[Dict[str, Any]]:
    """Fetch flights from FlightRadar24 (synchronous)"""
    try:
        flights = fr_api.get_flights(bounds=NL_BOUNDS)

        result = []
        for f in flights:
            # Skip ground vehicles and flights on ground
            if f.on_ground and f.ground_speed < 50:
                continue

            result.append({
                "id": f.id,
                "callsign": f.callsign or f.registration or "N/A",
                "lat": f.latitude,
                "lng": f.longitude,
                "altitude": f.altitude,  # feet
                "heading": f.heading,
                "speed": f.ground_speed,  # knots
                "vspeed": f.vertical_speed,  # ft/min
                "aircraft": f.aircraft_code or "???",
                "airline": f.airline_iata or "",
                "origin": f.origin_airport_iata or "",
                "destination": f.destination_airport_iata or "",
                "registration": f.registration or "",
                "on_ground": f.on_ground
            })

        print(f"FlightRadar24: {len(result)} aircraft in range")
        return result

    except Exception as e:
        print(f"FlightRadar24 error: {e}")
        return []


async def fetch_flight_positions() -> None:
    """Fetch flight positions (async wrapper)"""
    loop = asyncio.get_event_loop()
    flights = await loop.run_in_executor(None, fetch_flights_sync)

    _cache["flights"] = flights
    _cache["updated"] = datetime.now().strftime("%H:%M:%S")


async def get_flight_positions() -> Dict[str, Any]:
    """Get cached flight positions"""
    if not _cache["flights"]:
        await fetch_flight_positions()

    return {
        "flights": _cache["flights"],
        "count": len(_cache["flights"]),
        "updated": _cache["updated"]
    }
