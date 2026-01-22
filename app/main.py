from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as main_router
from app.api.sse import router as sse_router
from app.core.scheduler import setup_scheduler, initial_fetch, scheduler
from app.core.database import init_db, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await initial_fetch()
    setup_scheduler()
    yield
    # Shutdown
    scheduler.shutdown()
    await close_pool()


app = FastAPI(
    title="Amsterdam Monitor",
    description="Bloomberg-style dashboard for Amsterdam",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(main_router)
app.include_router(sse_router)
