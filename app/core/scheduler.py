import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import REFRESH_INTERVALS
from app.services import weather, news, transit, events, air_quality, markets
from app.services import hackernews, parking, trains, bikes, flights

scheduler = AsyncIOScheduler()

# SSE clients to notify on updates
sse_clients: set = set()


async def refresh_weather():
    await weather.fetch_weather()
    await notify_clients("weather")


async def refresh_news():
    await news.fetch_news()
    await notify_clients("news")


async def refresh_hackernews():
    await hackernews.fetch_hackernews()
    await notify_clients("hackernews")


async def refresh_transit():
    await transit.fetch_transit()
    await notify_clients("transit")


async def refresh_trains():
    await trains.fetch_trains()
    await notify_clients("trains")


async def refresh_events():
    await events.fetch_events()
    await notify_clients("events")


async def refresh_air_quality():
    await air_quality.fetch_air_quality()
    await notify_clients("air_quality")


async def refresh_markets():
    await markets.fetch_markets()
    await notify_clients("markets")


async def refresh_parking():
    await parking.fetch_parking()
    await notify_clients("parking")


async def refresh_bikes():
    await bikes.fetch_bikes()
    await notify_clients("bikes")


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
        refresh_hackernews,
        IntervalTrigger(seconds=REFRESH_INTERVALS["hackernews"]),
        id="hackernews",
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

    scheduler.start()


async def initial_fetch():
    """Fetch all data on startup."""
    await asyncio.gather(
        weather.fetch_weather(),
        news.fetch_news(),
        hackernews.fetch_hackernews(),
        transit.fetch_transit(),
        trains.fetch_trains(),
        events.fetch_events(),
        air_quality.fetch_air_quality(),
        markets.fetch_markets(),
        parking.fetch_parking(),
        bikes.fetch_bikes(),
        flights.fetch_flights(),
        return_exceptions=True,
    )
