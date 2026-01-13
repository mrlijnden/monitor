"""Map Data Service - Real-time transit positions for Amsterdam"""
import httpx
from datetime import datetime
from typing import List, Dict
from app.config import amsterdam_now

# OVapi endpoint for real-time vehicle positions
OVAPI_URL = "https://v0.ovapi.nl/vehicle"

# Amsterdam area bounds
AMS_BOUNDS = {
    "lat_min": 52.30,
    "lat_max": 52.42,
    "lng_min": 4.75,
    "lng_max": 5.05
}

async def get_transit_positions() -> Dict:
    """Get real-time GVB vehicle positions"""
    vehicles = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(OVAPI_URL)
                if response.status_code == 200:
                    data = response.json()
                    # Filter for Amsterdam area vehicles
                    for vehicle_id, vehicle in data.items():
                        if is_in_amsterdam(vehicle):
                            vehicles.append(parse_vehicle(vehicle_id, vehicle))
            except Exception as e:
                print(f"OVapi error: {e}")

    except Exception as e:
        print(f"Error fetching transit positions: {e}")

    # Return empty if no real data available (no sample data)
    return {
        "vehicles": vehicles[:50],  # Limit to 50 vehicles
        "updated": amsterdam_now().strftime("%H:%M:%S"),
        "count": len(vehicles)
    }

def is_in_amsterdam(vehicle: dict) -> bool:
    """Check if vehicle is in Amsterdam area"""
    lat = vehicle.get("Latitude", 0)
    lng = vehicle.get("Longitude", 0)
    return (AMS_BOUNDS["lat_min"] <= lat <= AMS_BOUNDS["lat_max"] and
            AMS_BOUNDS["lng_min"] <= lng <= AMS_BOUNDS["lng_max"])

def parse_vehicle(vehicle_id: str, vehicle: dict) -> dict:
    """Parse vehicle data to standardized format"""
    return {
        "id": vehicle_id,
        "lat": vehicle.get("Latitude"),
        "lng": vehicle.get("Longitude"),
        "line": vehicle.get("LinePlanningNumber", "?"),
        "type": get_vehicle_type(vehicle),
        "destination": vehicle.get("Destination", ""),
        "delay": vehicle.get("Delay", 0),
        "operator": vehicle.get("DataOwnerCode", "GVB")
    }

def get_vehicle_type(vehicle: dict) -> str:
    """Determine vehicle type"""
    line = str(vehicle.get("LinePlanningNumber", ""))
    if line.isdigit():
        num = int(line)
        if 1 <= num <= 17:
            return "tram"
        elif 50 <= num <= 54:
            return "metro"
    return "bus"


async def get_map_markers() -> Dict:
    """Get all markers for the map (landmarks, incidents, etc)"""
    return {
        "landmarks": [
            {"lat": 52.3791, "lng": 4.8980, "name": "Centraal Station", "type": "transit"},
            {"lat": 52.3702, "lng": 4.8952, "name": "Dam Square", "type": "landmark"},
            {"lat": 52.3080, "lng": 4.7621, "name": "Schiphol Airport", "type": "airport"},
            {"lat": 52.3600, "lng": 4.8852, "name": "Rijksmuseum", "type": "landmark"},
            {"lat": 52.3738, "lng": 4.8910, "name": "Anne Frank House", "type": "landmark"},
            {"lat": 52.3664, "lng": 4.8795, "name": "Vondelpark", "type": "park"},
        ],
        "updated": amsterdam_now().strftime("%H:%M:%S")
    }
