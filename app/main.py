"""Main FastAPI application for SiliconRoute."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.api.devices import router as devices_router
from app.api.system import router as system_router
from app.config import BASE_DIR
from app.db import engine, init_db
from app.devices import sync_devices_to_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("siliconroute")

FRONTEND_DIR: Path = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database and detect hardware on startup."""
    logger.info("Initializing SiliconRoute database schema (WAL mode)...")
    init_db()

    logger.info("Detecting hardware devices (CPU & DirectML adapters)...")
    with Session(engine) as session:
        devices = sync_devices_to_db(session)
        logger.info(
            "Detected %d hardware device(s): %s",
            len(devices),
            ", ".join(f"{d.key} ({d.label})" for d in devices),
        )

    yield

    logger.info("SiliconRoute application shutdown complete.")


app = FastAPI(
    title="SiliconRoute",
    description="Local-first, self-learning AI load balancer for laptops.",
    version="1.0.0",
    lifespan=lifespan,
)

# Register API routers
app.include_router(system_router)
app.include_router(devices_router)

# Mount static frontend at root (must be after API routers to avoid route collision)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
