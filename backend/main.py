"""
FastAPI application entry point.
"""
from __future__ import annotations

import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import ensure_secrets, get_config, load_config
from backend.database import init_db
from backend.realtime.sio_instance import sio
from backend.scheduler.scheduler import start_scheduler
from backend.utils.logger import setup_logger

import socketio
import httpx

# Shared async HTTP client — reused across all integrations for connection pooling
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialised")
    return _http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────
    global _http_client
    config = get_config()
    setup_logger(config.server.log_level.upper())
    _http_client = httpx.AsyncClient(timeout=15.0, verify=True)

    # Ensure directories exist (also done in run.py before import, belt-and-suspenders)
    for directory in [
        "data",
        "data/logs",
        "data/MediaCover",
        config.files.recycling_bin,
    ]:
        if directory:
            os.makedirs(directory, exist_ok=True)

    try:
        await init_db()
    except Exception as exc:
        from loguru import logger
        logger.critical(f"Database init failed: {exc}")
        raise
    start_scheduler()
    asyncio.create_task(_resume_downloads_after_startup())

    yield
    # ── Shutdown ─────────────────────────────────────────────────────
    from backend.scheduler.scheduler import stop_scheduler
    stop_scheduler()
    if _http_client:
        await _http_client.aclose()


async def _resume_downloads_after_startup() -> None:
    from loguru import logger

    await asyncio.sleep(2)
    try:
        from backend.core.download_workflow import resume_downloading_downloads

        resumed = await resume_downloading_downloads()
        if resumed:
            logger.info(f"Resumed {resumed} stuck downloading workflow(s)")
    except Exception as exc:
        logger.warning(f"Stuck download resume failed: {exc}")


app = FastAPI(
    title="Slimarr",
    version="1.2.0.0",
    description="Smart Usenet replacement manager for Plex movie libraries",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_config().server.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ───────────────────────────────────────────────────────
from backend.api.activity import router as activity_router
from backend.api.dashboard import router as dashboard_router
from backend.api.images import router as images_router
from backend.api.library import router as library_router
from backend.api.queue import router as queue_router
from backend.api.settings import router as settings_router
from backend.api.system import router as system_router
from backend.api.tv import router as tv_router
from backend.auth.router import router as auth_router

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=f"{API_PREFIX}/auth")
app.include_router(dashboard_router, prefix=API_PREFIX)
app.include_router(library_router, prefix=API_PREFIX)
app.include_router(activity_router, prefix=API_PREFIX)
app.include_router(settings_router, prefix=API_PREFIX)
app.include_router(queue_router, prefix=API_PREFIX)
app.include_router(system_router, prefix=API_PREFIX)
app.include_router(tv_router, prefix=API_PREFIX)
app.include_router(images_router, prefix=API_PREFIX)

# ── Frontend static files ─────────────────────────────────────────────
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
ASSETS_DIR = os.path.join(FRONTEND_DIST, "assets")

if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Serve root-level static files (logo.png, favicon, etc.) from dist/
if os.path.isdir(FRONTEND_DIST):
    app.mount("/static-root", StaticFiles(directory=FRONTEND_DIST), name="static-root")


@app.get("/logo.png", include_in_schema=False)
async def logo():
    path = os.path.join(FRONTEND_DIST, "logo.png")
    if os.path.isfile(path):
        return FileResponse(path)
    # Fallback to images/ directory
    path2 = os.path.join(os.path.dirname(__file__), "..", "images", "header-logo.PNG")
    if os.path.isfile(path2):
        return FileResponse(path2)
    from fastapi import HTTPException
    raise HTTPException(404)


@app.get("/favicon.png", include_in_schema=False)
async def favicon_png():
    path = os.path.join(FRONTEND_DIST, "favicon.png")
    if os.path.isfile(path):
        return FileResponse(path)
    # Fallback to source icon in development/source mode
    path2 = os.path.join(os.path.dirname(__file__), "..", "images", "icon.PNG")
    if os.path.isfile(path2):
        return FileResponse(path2)
    from fastapi import HTTPException
    raise HTTPException(404)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon_ico():
    path = os.path.join(os.path.dirname(__file__), "..", "images", "icon.ico")
    if os.path.isfile(path):
        return FileResponse(path)
    return await favicon_png()


@app.get("/", include_in_schema=False)
@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str = ""):
    index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return {"status": "Slimarr API running", "docs": "/docs"}


# ── Wrap with Socket.IO ──────────────────────────────────────────────
socket_app = socketio.ASGIApp(sio, app)
