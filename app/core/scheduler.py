import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import REFRESH_INTERVALS
from app.services import weather, news, transit, events, air_quality, markets
from app.services import parking, trains, bikes, flights, vision, cameras, emergency, traffic
from app.services import flightradar
from app.core.database import save_panel_data, cleanup_old_panel_data
from app.core.cache import cache

scheduler = AsyncIOScheduler()

# SSE clients to notify on updates
sse_clients: set = set()

# Panels to persist to database (skip high-frequency ones like flightradar)
DB_PERSIST_PANELS = {
    "weather", "news", "transit", "trains", "events", "air_quality",
    "markets", "parking", "bikes", "flights", "emergency", "traffic"
}


async def persist_to_db(panel: str):
    """Save panel data to database if enabled"""
    if panel in DB_PERSIST_PANELS:
        data = cache.get(panel)
        if data:
            await save_panel_data(panel, data)


async def refresh_weather():
    await weather.fetch_weather()
    await persist_to_db("weather")
    await notify_clients("weather")


async def refresh_news():
    await news.fetch_news()
    await persist_to_db("news")
    await notify_clients("news")


async def refresh_transit():
    await transit.fetch_transit()
    await persist_to_db("transit")
    await notify_clients("transit")


async def refresh_trains():
    await trains.fetch_trains()
    await persist_to_db("trains")
    await notify_clients("trains")


async def refresh_events():
    await events.fetch_events()
    await persist_to_db("events")
    await notify_clients("events")


async def refresh_air_quality():
    await air_quality.fetch_air_quality()
    await persist_to_db("air_quality")
    await notify_clients("air_quality")


async def refresh_markets():
    await markets.fetch_markets()
    await persist_to_db("markets")
    await notify_clients("markets")


async def refresh_parking():
    await parking.fetch_parking()
    await persist_to_db("parking")
    await notify_clients("parking")


async def refresh_bikes():
    await bikes.fetch_bikes()
    await persist_to_db("bikes")
    await notify_clients("bikes")


async def refresh_flights():
    await flights.fetch_flights()
    await persist_to_db("flights")
    await notify_clients("flights")


# Vision is now on-demand only (triggered when user visits the page)
# This saves API costs - detection only happens when someone views cameras


async def refresh_emergency():
    await emergency.fetch_emergency()
    await persist_to_db("emergency")
    await notify_clients("emergency")


async def refresh_traffic():
    await traffic.fetch_traffic()
    await persist_to_db("traffic")
    await notify_clients("traffic")


async def refresh_flightradar():
    await flightradar.fetch_flight_positions()
    # Skip DB persist for flightradar - too frequent (15 sec)
    await notify_clients("flightradar")


async def notify_clients(panel: str):
    """Notify all SSE clients about an update."""
    for queue in list(sse_clients):
        try:
            await queue.put(panel)
        except Exception:
            sse_clients.discard(queue)


def setup_scheduler():
    """Configure and start the scheduler."""
    scheduler.add_job(
        refresh_weather,
        IntervalTrigger(seconds=REFRESH_INTERVALS["weather"]),
        id="weather",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_news,
        IntervalTrigger(seconds=REFRESH_INTERVALS["news"]),
        id="news",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_transit,
        IntervalTrigger(seconds=REFRESH_INTERVALS["transit"]),
        id="transit",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_trains,
        IntervalTrigger(seconds=REFRESH_INTERVALS["trains"]),
        id="trains",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_events,
        IntervalTrigger(seconds=REFRESH_INTERVALS["events"]),
        id="events",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_air_quality,
        IntervalTrigger(seconds=REFRESH_INTERVALS["air_quality"]),
        id="air_quality",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_markets,
        IntervalTrigger(seconds=REFRESH_INTERVALS["markets"]),
        id="markets",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_parking,
        IntervalTrigger(seconds=REFRESH_INTERVALS["parking"]),
        id="parking",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_bikes,
        IntervalTrigger(seconds=REFRESH_INTERVALS["bikes"]),
        id="bikes",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_flights,
        IntervalTrigger(seconds=REFRESH_INTERVALS["flights"]),
        id="flights",
        replace_existing=True,
    )
    # Vision removed from scheduler - now on-demand only to save API costs
    scheduler.add_job(
        refresh_emergency,
        IntervalTrigger(seconds=REFRESH_INTERVALS["emergency"]),
        id="emergency",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_traffic,
        IntervalTrigger(seconds=REFRESH_INTERVALS["traffic"]),
        id="traffic",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_flightradar,
        IntervalTrigger(seconds=REFRESH_INTERVALS["flightradar"]),
        id="flightradar",
        replace_existing=True,
    )

    # Daily cleanup of old panel data (keep 7 days)
    scheduler.add_job(
        cleanup_old_panel_data,
        IntervalTrigger(hours=24),
        id="db_cleanup",
        replace_existing=True,
    )

    scheduler.start()


async def initial_fetch():
    """Fetch all data on startup."""
    await asyncio.gather(
        weather.fetch_weather(),
        news.fetch_news(),
        transit.fetch_transit(),
        trains.fetch_trains(),
        events.fetch_events(),
        air_quality.fetch_air_quality(),
        markets.fetch_markets(),
        parking.fetch_parking(),
        bikes.fetch_bikes(),
        flights.fetch_flights(),
        emergency.fetch_emergency(),
        traffic.fetch_traffic(),
        flightradar.fetch_flight_positions(),
        return_exceptions=True,
    )
