from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services import weather, news, transit, events, air_quality, markets
from app.services import hackernews, parking, trains, bikes
from app.services import emergency, cameras, flights, ticker, map_data

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main dashboard."""
    data = {
        "weather": await weather.get_weather(),
        "news": await news.get_news(),
        "hackernews": await hackernews.get_hackernews(),
        "transit": await transit.get_transit(),
        "trains": await trains.get_trains(),
        "events": await events.get_events(),
        "air_quality": await air_quality.get_air_quality(),
        "markets": await markets.get_markets(),
        "parking": await parking.get_parking(),
        "bikes": await bikes.get_bikes(),
    }
    return templates.TemplateResponse("index.html", {"request": request, **data})


# JSON API endpoints
@router.get("/api/weather")
async def api_weather():
    return await weather.get_weather()


@router.get("/api/news")
async def api_news():
    return await news.get_news()


@router.get("/api/hackernews")
async def api_hackernews():
    return await hackernews.get_hackernews()


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


@router.get("/partial/hackernews", response_class=HTMLResponse)
async def partial_hackernews(request: Request):
    data = await hackernews.get_hackernews()
    return templates.TemplateResponse("partials/hackernews.html", {"request": request, "hackernews": data})


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
    data = await cameras.get_cameras_data()
    return templates.TemplateResponse("partials/cameras.html", {"request": request, "cameras": data})


@router.get("/partial/flights", response_class=HTMLResponse)
async def partial_flights(request: Request):
    data = await flights.get_flights_data()
    return templates.TemplateResponse("partials/flights.html", {"request": request, "flights": data})


@router.get("/partial/ticker", response_class=HTMLResponse)
async def partial_ticker(request: Request):
    data = await ticker.get_ticker_data()
    return templates.TemplateResponse("partials/ticker.html", {"request": request, "ticker": data})


@router.get("/api/map/vehicles")
async def api_map_vehicles():
    """Get real-time transit vehicle positions"""
    return await map_data.get_transit_positions()


@router.get("/api/map/markers")
async def api_map_markers():
    """Get map markers (landmarks, incidents)"""
    return await map_data.get_map_markers()
