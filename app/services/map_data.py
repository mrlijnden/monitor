"""Map Data Service - Real-time transit positions for Amsterdam"""
import httpx
from datetime import datetime
from typing import List, Dict
import random

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

    # If no real data, generate sample positions
    if not vehicles:
        vehicles = generate_sample_vehicles()

    return {
        "vehicles": vehicles[:50],  # Limit to 50 vehicles
        "updated": datetime.now().strftime("%H:%M:%S"),
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

def generate_sample_vehicles() -> List[Dict]:
    """Generate sample vehicle positions for demo"""
    vehicles = []

    # Tram lines with typical routes
    tram_routes = [
        {"line": "2", "start": (52.3791, 4.8980), "end": (52.3560, 4.8930)},
        {"line": "5", "start": (52.3791, 4.8980), "end": (52.3400, 4.8700)},
        {"line": "12", "start": (52.3791, 4.8980), "end": (52.3650, 4.9400)},
        {"line": "13", "start": (52.3791, 4.8980), "end": (52.3850, 4.8700)},
        {"line": "14", "start": (52.3800, 4.9100), "end": (52.3550, 4.9200)},
        {"line": "17", "start": (52.3791, 4.8980), "end": (52.3450, 4.8550)},
        {"line": "24", "start": (52.3791, 4.8980), "end": (52.3700, 4.9350)},
    ]

    # Metro lines
    metro_routes = [
        {"line": "51", "start": (52.3791, 4.8980), "end": (52.3100, 4.9600)},
        {"line": "52", "start": (52.3950, 4.9200), "end": (52.3400, 4.8900)},
        {"line": "53", "start": (52.3791, 4.8980), "end": (52.3000, 4.9800)},
        {"line": "54", "start": (52.3791, 4.8980), "end": (52.3200, 4.9400)},
    ]

    # Generate positions along routes
    for route in tram_routes:
        for i in range(3):  # 3 vehicles per line
            progress = random.random()
            lat = route["start"][0] + (route["end"][0] - route["start"][0]) * progress
            lng = route["start"][1] + (route["end"][1] - route["start"][1]) * progress
            lat += random.uniform(-0.002, 0.002)  # Add some variance
            lng += random.uniform(-0.002, 0.002)

            vehicles.append({
                "id": f"tram_{route['line']}_{i}",
                "lat": lat,
                "lng": lng,
                "line": route["line"],
                "type": "tram",
                "destination": random.choice(["Centraal", "Amstelstation", "Sloterdijk", "RAI"]),
                "delay": random.choice([0, 0, 0, 1, 2, 3, 5]),
                "operator": "GVB"
            })

    for route in metro_routes:
        for i in range(2):  # 2 vehicles per metro line
            progress = random.random()
            lat = route["start"][0] + (route["end"][0] - route["start"][0]) * progress
            lng = route["start"][1] + (route["end"][1] - route["start"][1]) * progress

            vehicles.append({
                "id": f"metro_{route['line']}_{i}",
                "lat": lat,
                "lng": lng,
                "line": route["line"],
                "type": "metro",
                "destination": random.choice(["Zuid", "Centraal", "Isolatorweg", "Gein"]),
                "delay": 0,
                "operator": "GVB"
            })

    # Add some ferries
    ferry_positions = [
        (52.3815, 4.9010),  # Buiksloterweg
        (52.3840, 4.9040),  # NDSM
        (52.3830, 4.9140),  # IJplein
    ]

    for i, pos in enumerate(ferry_positions):
        vehicles.append({
            "id": f"ferry_{i}",
            "lat": pos[0] + random.uniform(-0.001, 0.001),
            "lng": pos[1] + random.uniform(-0.001, 0.001),
            "line": f"F{i+1}",
            "type": "ferry",
            "destination": "Centraal" if random.random() > 0.5 else "Noord",
            "delay": 0,
            "operator": "GVB"
        })

    return vehicles

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
        "updated": datetime.now().strftime("%H:%M:%S")
    }
