import asyncio
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.core.scheduler import sse_clients

router = APIRouter()


async def event_generator(queue: asyncio.Queue):
    """Generate SSE events from the queue."""
    try:
        while True:
            panel = await queue.get()
            yield {
                "event": "update",
                "data": panel,
            }
    except asyncio.CancelledError:
        pass


@router.get("/sse/updates")
async def sse_updates():
    """SSE endpoint for real-time panel updates."""
    queue = asyncio.Queue()
    sse_clients.add(queue)

    async def cleanup():
        sse_clients.discard(queue)

    return EventSourceResponse(
        event_generator(queue),
        ping=30,
    )
