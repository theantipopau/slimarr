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
    from backend.core.scanner import is_scan_running, scan_library
    from backend.core.orchestrator import is_running as is_cycle_running
    if is_scan_running() or is_cycle_running():
        return {"status": "already_running"}
    background.add_task(scan_library)
    return {"status": "scan_started"}


@router.post("/cleanup")
async def trigger_cleanup(background: BackgroundTasks, user=Depends(get_current_user)):
    """Trigger a duplicate file cleanup in the library."""
    from backend.core.cleanup import scan_and_clean_duplicates
    background.add_task(scan_and_clean_duplicates)
    return {"status": "cleanup_started"}


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
        if not config.radarr.url.startswith(("http://", "https://")):
            results["radarr"] = {"success": False, "error": "URL missing http:// or https:// prefix"}
        else:
            try:
                from backend.integrations.radarr import RadarrClient
                results["radarr"] = await RadarrClient().test_connection()
            except Exception as e:
                results["radarr"] = {"success": False, "error": str(e)}
    elif not config.radarr.enabled:
        results["radarr"] = {"success": False, "error": "Disabled"}
    else:
        results["radarr"] = {"success": False, "error": "Missing URL or API key"}

    # Sonarr
    if config.sonarr.enabled and config.sonarr.url and config.sonarr.api_key:
        if not config.sonarr.url.startswith(("http://", "https://")):
            results["sonarr"] = {"success": False, "error": "URL missing http:// or https:// prefix"}
        else:
            try:
                from backend.integrations.sonarr import SonarrClient
                results["sonarr"] = await SonarrClient().test_connection()
            except Exception as e:
                results["sonarr"] = {"success": False, "error": str(e)}
    elif not config.sonarr.enabled:
        results["sonarr"] = {"success": False, "error": "Disabled"}
    else:
        results["sonarr"] = {"success": False, "error": "Missing URL or API key"}

    # Prowlarr
    if config.prowlarr.enabled and config.prowlarr.url and config.prowlarr.api_key:
        if not config.prowlarr.url.startswith(("http://", "https://")):
            results["prowlarr"] = {"success": False, "error": "URL missing http:// or https:// prefix"}
        else:
            try:
                from backend.integrations.prowlarr import ProwlarrClient
                results["prowlarr"] = await ProwlarrClient().test_connection()
            except Exception as e:
                results["prowlarr"] = {"success": False, "error": str(e)}
    elif not config.prowlarr.enabled:
        results["prowlarr"] = {"success": False, "error": "Disabled"}
    else:
        results["prowlarr"] = {"success": False, "error": "Missing URL or API key"}

    # TMDB
    if config.tmdb.api_key:
        try:
            from backend.integrations.tmdb import TMDBClient
            results["tmdb"] = await TMDBClient().test_connection()
        except Exception as e:
            results["tmdb"] = {"success": False, "error": str(e)}
    else:
        results["tmdb"] = {"success": False, "error": "Disabled"}

    # Indexers
    indexer_results = []
    for idx in config.indexers:
        if not idx.name or not idx.url:
            continue
        if not idx.url.startswith(("http://", "https://")):
            indexer_results.append({"name": idx.name, "success": False, "error": "Invalid URL"})
            continue
        try:
            from backend.integrations.newznab import NewznabClient
            status = await NewznabClient(idx).test_connection()
            indexer_results.append({"name": idx.name, "success": status.get("success", False), "error": status.get("error")})
        except Exception as e:
            indexer_results.append({"name": idx.name, "success": False, "error": str(e)})
    results["indexers"] = indexer_results

    return results
