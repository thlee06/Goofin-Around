from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.database import init_db
from app.scrapers.scheduler import start_scheduler, stop_scheduler
from app.services.search_service import ensure_index


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    ensure_index()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Columbia Events Hub",
        description="Aggregated events from across Columbia University departments.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    from app.routers import pages, events, search, export
    app.include_router(pages.router)
    app.include_router(events.router, prefix="/events")
    app.include_router(search.router)
    app.include_router(export.router)

    return app
