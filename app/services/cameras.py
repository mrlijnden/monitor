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
        "video_id": "Gd9d4q6WvUY",
    },
    {
        "id": "centraal",
        "name": "Amsterdam Centraal",
        "location": "Centrum",
        "type": "youtube",
        "embed": "https://www.youtube.com/embed/2tgHBRFHMm8?autoplay=1&mute=1",  # Centraal Station live
        "video_id": "2tgHBRFHMm8",
    },
    {
        "id": "live3",
        "name": "Live Camera",
        "location": "Amsterdam",
        "type": "youtube",
        "embed": "https://www.youtube.com/embed/9Pm6Ji6tm7s?autoplay=1&mute=1",  # Live camera feed
        "video_id": "9Pm6Ji6tm7s",
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

async def get_cameras_data(panel_index: int = 0) -> Dict:
    """Get available camera feeds for a specific panel
    
    Args:
        panel_index: 0 for first panel, 1 for second panel
    """
    cameras = []

    for cam in AMSTERDAM_CAMERAS:
        cameras.append({
            "id": cam["id"],
            "name": cam["name"],
            "location": cam["location"],
            "type": cam.get("type", "youtube"),
            "embed": cam.get("embed"),
            "image": cam.get("url"),
            "video_id": cam.get("video_id"),
            "refresh": cam.get("refresh", 0)
        })

    # For second panel, start at a different camera index
    start_index = panel_index if panel_index < len(cameras) else 0

    return {
        "cameras": cameras,
        "current_index": start_index,
        "auto_rotate": True,
        "rotate_interval": 30,  # seconds (longer for video streams)
        "panel_id": f"panel-cameras{panel_index + 1 if panel_index > 0 else ''}"
    }

def get_camera_list() -> List[Dict]:
    """Get list of all cameras"""
    return AMSTERDAM_CAMERAS
