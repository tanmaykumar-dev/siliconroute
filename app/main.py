"""Main FastAPI application for SiliconRoute."""

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.api.analysis import router as analysis_router
from app.api.benchmarks import router as benchmarks_router
from app.api.decisions import router as decisions_router
from app.api.devices import router as devices_router
from app.api.fits import router as fits_router
from app.api.models import router as models_router
from app.api.runs import router as runs_router
from app.api.system import router as system_router
from app.config import BASE_DIR, DATA_DIR, DB_PATH
from app.db import engine, init_db
from app.devices import sync_devices_to_db
from app.jobs import start_worker, stop_worker
from app.telemetry import (
    loop_holder,
    router as telemetry_router,
    start_sampler,
    stop_sampler,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("siliconroute")

FRONTEND_DIR: Path = BASE_DIR / "frontend"
SITE_DIR: Path = BASE_DIR / "site"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize DB, detect hardware, start job worker and telemetry."""
    # Seed working database from frozen benchmark database on fresh clone
    frozen_db = DATA_DIR / "final" / "siliconroute_final.db"
    if not DB_PATH.exists() and frozen_db.exists():
        import shutil
        logger.info("Seeding working database from frozen benchmark database (%s)...", frozen_db)
        shutil.copy2(frozen_db, DB_PATH)

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

    logger.info("Starting background single-job worker...")
    start_worker()

    logger.info("Starting background 1 Hz telemetry sampler...")
    loop_holder["loop"] = asyncio.get_running_loop()
    start_sampler()

    yield

    logger.info("Stopping telemetry sampler...")
    stop_sampler()

    logger.info("Stopping background job worker...")
    stop_worker()
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
app.include_router(models_router)
app.include_router(benchmarks_router)
app.include_router(runs_router)
app.include_router(telemetry_router)
app.include_router(fits_router)
app.include_router(analysis_router)
app.include_router(decisions_router)

# Mount static site and frontend (must be after API routers to avoid route collision)
if SITE_DIR.exists():
    app.mount("/site", StaticFiles(directory=str(SITE_DIR), html=True), name="site")
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
