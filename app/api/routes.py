from typing import Optional
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services import weather, news, transit, events, air_quality, markets
from app.services import parking, trains, bikes
from app.services import emergency, cameras, flights, ticker, map_data, vision, traffic
from app.services import flightradar
from app.core.database import get_recent_detections, get_detection_stats, get_detections_timeline, get_panel_history, get_latest_panel_data

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main dashboard."""
    # Detect if running locally (Flightradar24 blocks iframes on localhost)
    is_local = request.url.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]
    
    data = {
        "weather": await weather.get_weather(),
        "news": await news.get_news(),
        "transit": await transit.get_transit(),
        "trains": await trains.get_trains(),
        "events": await events.get_events(),
        "air_quality": await air_quality.get_air_quality(),
        "markets": await markets.get_markets(),
        "parking": await parking.get_parking(),
        "bikes": await bikes.get_bikes(),
        "is_local": is_local,
    }
    return templates.TemplateResponse("index.html", {"request": request, **data})


# JSON API endpoints
@router.get("/api/weather")
async def api_weather():
    return await weather.get_weather()


@router.get("/api/news")
async def api_news():
    return await news.get_news()


@router.get("/api/transit")
async def api_transit():
    return await transit.get_transit()


@router.get("/api/trains")
async def api_trains():
    return await trains.get_trains()


@router.get("/api/events")
async def api_events():
    return await events.get_events()


@router.get("/api/air_quality")
async def api_air_quality():
    return await air_quality.get_air_quality()


@router.get("/api/markets")
async def api_markets():
    return await markets.get_markets()


@router.get("/api/parking")
async def api_parking():
    return await parking.get_parking()


@router.get("/api/bikes")
async def api_bikes():
    return await bikes.get_bikes()


# Partial templates for htmx updates
@router.get("/partial/weather", response_class=HTMLResponse)
async def partial_weather(request: Request):
    data = await weather.get_weather()
    return templates.TemplateResponse("partials/weather.html", {"request": request, "weather": data})


@router.get("/partial/news", response_class=HTMLResponse)
async def partial_news(request: Request):
    data = await news.get_news()
    return templates.TemplateResponse("partials/news.html", {"request": request, "news": data})


@router.get("/partial/transit", response_class=HTMLResponse)
async def partial_transit(request: Request):
    data = await transit.get_transit()
    return templates.TemplateResponse("partials/transit.html", {"request": request, "transit": data})


@router.get("/partial/trains", response_class=HTMLResponse)
async def partial_trains(request: Request):
    data = await trains.get_trains()
    return templates.TemplateResponse("partials/trains.html", {"request": request, "trains": data})


@router.get("/partial/events", response_class=HTMLResponse)
async def partial_events(request: Request):
    data = await events.get_events()
    return templates.TemplateResponse("partials/events.html", {"request": request, "events": data})


@router.get("/partial/air_quality", response_class=HTMLResponse)
async def partial_air_quality(request: Request):
    data = await air_quality.get_air_quality()
    return templates.TemplateResponse("partials/air_quality.html", {"request": request, "air_quality": data})


@router.get("/partial/markets", response_class=HTMLResponse)
async def partial_markets(request: Request):
    data = await markets.get_markets()
    return templates.TemplateResponse("partials/markets.html", {"request": request, "markets": data})


@router.get("/partial/parking", response_class=HTMLResponse)
async def partial_parking(request: Request):
    data = await parking.get_parking()
    return templates.TemplateResponse("partials/parking.html", {"request": request, "parking": data})


@router.get("/partial/bikes", response_class=HTMLResponse)
async def partial_bikes(request: Request):
    data = await bikes.get_bikes()
    return templates.TemplateResponse("partials/bikes.html", {"request": request, "bikes": data})


# New wild features
@router.get("/api/emergency")
async def api_emergency():
    return await emergency.get_emergency_data()


@router.get("/api/cameras")
async def api_cameras():
    return await cameras.get_cameras_data()


@router.get("/api/flights")
async def api_flights():
    return await flights.get_flights_data()


@router.get("/api/ticker")
async def api_ticker():
    return await ticker.get_ticker_data()


@router.get("/partial/emergency", response_class=HTMLResponse)
async def partial_emergency(request: Request):
    data = await emergency.get_emergency_data()
    return templates.TemplateResponse("partials/emergency.html", {"request": request, "emergency": data})


@router.get("/partial/cameras", response_class=HTMLResponse)
async def partial_cameras(request: Request):
    data = await cameras.get_cameras_data(panel_index=0)
    return templates.TemplateResponse("partials/cameras.html", {"request": request, "cameras": data, "panel_suffix": ""})


@router.get("/partial/cameras2", response_class=HTMLResponse)
async def partial_cameras2(request: Request):
    data = await cameras.get_cameras_data(panel_index=1)
    return templates.TemplateResponse("partials/cameras.html", {"request": request, "cameras": data, "panel_suffix": "2"})


@router.get("/partial/flights", response_class=HTMLResponse)
async def partial_flights(request: Request):
    data = await flights.get_flights_data()
    return templates.TemplateResponse("partials/flights.html", {"request": request, "flights": data})


@router.get("/partial/ticker", response_class=HTMLResponse)
async def partial_ticker(request: Request):
    data = await ticker.get_ticker_data()
    return templates.TemplateResponse("partials/ticker.html", {"request": request, "ticker": data})


@router.get("/api/traffic")
async def api_traffic():
    """Get ANWB traffic jams and incidents"""
    return await traffic.get_traffic()


@router.get("/api/map/vehicles")
async def api_map_vehicles():
    """Get real-time transit vehicle positions"""
    return await map_data.get_transit_positions()


@router.get("/api/map/markers")
async def api_map_markers():
    """Get map markers (landmarks, incidents)"""
    return await map_data.get_map_markers()


@router.get("/api/vision/{camera_id}")
async def api_vision_detection(camera_id: str):
    """Get object detection results for a camera"""
    return await vision.get_camera_detections(camera_id)


@router.get("/partial/vision/{camera_id}", response_class=HTMLResponse)
async def partial_vision_detection(request: Request, camera_id: str):
    """Get vision detection HTML partial"""
    data = await vision.get_camera_detections(camera_id)
    return templates.TemplateResponse("partials/vision_detection.html", {"request": request, "detection": data})


@router.get("/api/vision/{camera_id}/image")
async def api_vision_image(camera_id: str):
    """Get camera frame with bounding boxes drawn on detected objects"""
    image_bytes = await vision.get_annotated_frame(camera_id)
    if image_bytes:
        return Response(content=image_bytes, media_type="image/jpeg")
    return Response(content=b"", status_code=404)


@router.get("/partial/ai_detection/{camera_id}", response_class=HTMLResponse)
async def partial_ai_detection(request: Request, camera_id: str):
    """Get AI detection panel HTML partial"""
    return templates.TemplateResponse("partials/ai_detection.html", {
        "request": request,
        "camera_id": camera_id,
        "panel_suffix": f"_{camera_id}"
    })


@router.get("/api/detections")
async def api_detections(camera_id: Optional[str] = None, limit: int = 100):
    """Get recent detections from database"""
    detections = await get_recent_detections(camera_id=camera_id, limit=limit)
    # Convert datetime objects to strings for JSON serialization
    for d in detections:
        if d.get('detected_at'):
            d['detected_at'] = d['detected_at'].isoformat()
    return {"detections": detections, "count": len(detections)}


@router.get("/api/detections/stats")
async def api_detection_stats(camera_id: Optional[str] = None):
    """Get detection statistics"""
    stats = await get_detection_stats(camera_id=camera_id)
    # Convert datetime objects to strings
    if stats.get('first_detection'):
        stats['first_detection'] = stats['first_detection'].isoformat()
    if stats.get('last_detection'):
        stats['last_detection'] = stats['last_detection'].isoformat()
    if stats.get('avg_objects'):
        stats['avg_objects'] = float(stats['avg_objects'])
    return stats


@router.get("/api/detections/timeline")
async def api_detections_timeline(hours: int = 24):
    """Get hourly detection counts for both cameras over time"""
    return await get_detections_timeline(hours=hours)


@router.get("/api/map/flights")
async def api_map_flights():
    """Get live flight positions from FlightRadar24"""
    return await flightradar.get_flight_positions()


# Historical data endpoints
VALID_PANELS = {
    "weather", "news", "transit", "trains", "events", "air_quality",
    "markets", "parking", "bikes", "flights", "emergency", "traffic"
}


@router.get("/api/history/{panel_name}")
async def api_panel_history(panel_name: str, hours: int = 24, limit: int = 100):
    """Get historical data for a panel (requires DATABASE_URL)"""
    if panel_name not in VALID_PANELS:
        return {"error": f"Invalid panel. Valid panels: {', '.join(sorted(VALID_PANELS))}"}

    history = await get_panel_history(panel_name, hours=hours, limit=limit)
    return {
        "panel": panel_name,
        "hours": hours,
        "count": len(history),
        "history": history
    }


@router.get("/api/history/{panel_name}/latest")
async def api_panel_latest_from_db(panel_name: str):
    """Get the most recent data for a panel from database (fallback endpoint)"""
    if panel_name not in VALID_PANELS:
        return {"error": f"Invalid panel. Valid panels: {', '.join(sorted(VALID_PANELS))}"}

    data = await get_latest_panel_data(panel_name)
    if data:
        return {"panel": panel_name, "data": data, "source": "database"}
    return {"panel": panel_name, "data": None, "source": "database", "error": "No data found"}
