"""System/health API routes."""
from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends

from backend.auth.dependencies import get_current_user
from backend.core.orchestrator import get_status, is_running, request_stop
from backend.scheduler.scheduler import get_scheduler, list_jobs

router = APIRouter(prefix="/system", tags=["system"])

_start_time = datetime.now(timezone.utc)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/info")
async def get_system_info(user=Depends(get_current_user)):
    """Return version, uptime, DB size, and platform info."""
    from backend.config import get_config
    cfg = get_config()
    db_path = "data/slimarr.db"
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    uptime_seconds = int((datetime.now(timezone.utc) - _start_time).total_seconds())

    return {
        "version": "1.0.0",
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "uptime_seconds": uptime_seconds,
        "db_size_bytes": db_size,
        "port": cfg.server.port,
    }


@router.get("/status")
async def get_system_status(user=Depends(get_current_user)):
    return {
        "cycle": get_status(),
        "scheduler_running": get_scheduler().running if get_scheduler() else False,
        "jobs": list_jobs(),
    }


@router.get("/tasks")
async def list_tasks(user=Depends(get_current_user)):
    return list_jobs()


@router.post("/tasks/{task_id}/run")
async def run_task(task_id: str, background: BackgroundTasks, user=Depends(get_current_user)):
    scheduler = get_scheduler()
    job = scheduler.get_job(task_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    background.add_task(job.func)
    return {"status": "triggered", "task_id": task_id}


@router.post("/scan")
async def trigger_scan(background: BackgroundTasks, user=Depends(get_current_user)):
    """Trigger a full library scan in the background."""
    from backend.core.scanner import scan_library
    background.add_task(scan_library)
    return {"status": "scan_started"}


@router.post("/cycle/start")
async def start_cycle(background: BackgroundTasks, user=Depends(get_current_user)):
    if is_running():
        return {"status": "already_running"}
    from backend.core.orchestrator import run_full_cycle
    background.add_task(run_full_cycle)
    return {"status": "started"}


@router.post("/cycle/stop")
async def stop_cycle(user=Depends(get_current_user)):
    if not is_running():
        return {"status": "not_running"}
    request_stop()
    return {"status": "stop_requested"}


@router.get("/health/services")
async def services_health(user=Depends(get_current_user)):
    """Quick connectivity check for all configured integrations."""
    from backend.config import get_config
    config = get_config()
    results: dict = {}

    # Plex
    if config.plex.url and config.plex.token:
        try:
            from backend.integrations.plex import PlexClient
            results["plex"] = PlexClient().test_connection()
        except Exception as e:
            results["plex"] = {"success": False, "error": str(e)}
    else:
        results["plex"] = {"success": False, "error": "Not configured"}

    # SABnzbd
    if config.sabnzbd.url and config.sabnzbd.api_key:
        try:
            from backend.integrations.sabnzbd import SABnzbdClient
            results["sabnzbd"] = await SABnzbdClient().test_connection()
        except Exception as e:
            results["sabnzbd"] = {"success": False, "error": str(e)}
    else:
        results["sabnzbd"] = {"success": False, "error": "Not configured"}

    # Radarr
    if config.radarr.enabled and config.radarr.url and config.radarr.api_key:
        try:
            from backend.integrations.radarr import RadarrClient
            results["radarr"] = await RadarrClient().test_connection()
        except Exception as e:
            results["radarr"] = {"success": False, "error": str(e)}
    else:
        results["radarr"] = {"success": False, "error": "Not configured" if not config.radarr.enabled else "Missing URL/key"}

    # Prowlarr
    if config.prowlarr.enabled and config.prowlarr.url and config.prowlarr.api_key:
        try:
            from backend.integrations.prowlarr import ProwlarrClient
            results["prowlarr"] = await ProwlarrClient().test_connection()
        except Exception as e:
            results["prowlarr"] = {"success": False, "error": str(e)}
    else:
        results["prowlarr"] = {"success": False, "error": "Not configured" if not config.prowlarr.enabled else "Missing URL/key"}

    # TMDB
    if config.tmdb.api_key:
        try:
            from backend.integrations.tmdb import TMDBClient
            results["tmdb"] = await TMDBClient().test_connection()
        except Exception as e:
            results["tmdb"] = {"success": False, "error": str(e)}
    else:
        results["tmdb"] = {"success": False, "error": "Not configured"}

    return results
