"""Amsterdam Live Cameras Service - Real webcam feeds"""
from typing import List, Dict

# Real Amsterdam webcam feeds
# These are public webcams with auto-refreshing images or streams
AMSTERDAM_CAMERAS = [
    {
        "id": "dam",
        "name": "Dam Square",
        "location": "Centrum",
        "type": "youtube",
        "embed": "https://www.youtube.com/embed/Gd9d4q6WvUY?autoplay=1&mute=1",  # Dam Square 24/7 live
    },
    {
        "id": "centraal",
        "name": "Amsterdam Centraal",
        "location": "Centrum",
        "type": "youtube",
        "embed": "https://www.youtube.com/embed/2tgHBRFHMm8?autoplay=1&mute=1",  # Centraal Station live
    },
]

# Alternative: webcam image URLs that refresh
WEBCAM_IMAGES = [
    {
        "id": "a10",
        "name": "A10 Ring",
        "location": "Highway",
        "type": "image",
        "url": "https://webcam.arion.nl/beelden/A10.jpg",
        "refresh": 30
    },
]

async def get_cameras_data() -> Dict:
    """Get available camera feeds"""
    cameras = []

    for cam in AMSTERDAM_CAMERAS:
        cameras.append({
            "id": cam["id"],
            "name": cam["name"],
            "location": cam["location"],
            "type": cam.get("type", "youtube"),
            "embed": cam.get("embed"),
            "image": cam.get("url"),
            "refresh": cam.get("refresh", 0)
        })

    return {
        "cameras": cameras,
        "current_index": 0,
        "auto_rotate": True,
        "rotate_interval": 30  # seconds (longer for video streams)
    }

def get_camera_list() -> List[Dict]:
    """Get list of all cameras"""
    return AMSTERDAM_CAMERAS
