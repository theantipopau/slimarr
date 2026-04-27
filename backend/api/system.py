"""System/health API routes."""
from __future__ import annotations

import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import func, select

from backend.auth.dependencies import get_current_user
from backend.core.orchestrator import get_status, is_running, request_stop
from backend.database import DecisionAuditLog, Download, Movie, async_session
from backend.scheduler.scheduler import get_scheduler, list_jobs

router = APIRouter(prefix="/system", tags=["system"])

_start_time = datetime.now(timezone.utc)


CURRENT_VERSION = "1.0.0.3"
GITHUB_REPO = "theantipopau/slimarr"


def _get_recycling_bin_path() -> str:
    from backend.config import get_config
    cfg = get_config()
    return (cfg.files.recycling_bin or "").strip()


def _dir_stats(path: str) -> tuple[int, int]:
    """Return (files_count, total_bytes) for a directory tree."""
    files_count = 0
    total_bytes = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            files_count += 1
            file_path = os.path.join(root, name)
            try:
                total_bytes += os.path.getsize(file_path)
            except OSError:
                # Ignore unreadable files but keep scanning
                pass
    return files_count, total_bytes

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
        "version": CURRENT_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "uptime_seconds": uptime_seconds,
        "db_size_bytes": db_size,
        "port": cfg.server.port,
    }


@router.get("/update-check")
async def check_for_update(user=Depends(get_current_user)):
    """Check GitHub releases for a newer version."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            )
            if resp.status_code == 404:
                # No releases published yet
                return {"update_available": False, "current": CURRENT_VERSION, "latest": CURRENT_VERSION}
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"update_available": False, "current": CURRENT_VERSION, "error": str(e)}

    latest_tag = data.get("tag_name", "").lstrip("v")
    latest_name = data.get("name", latest_tag)
    release_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")
    published_at = data.get("published_at", "")

    def _version_tuple(v: str):
        try:
            return tuple(int(x) for x in v.split("."))
        except Exception:
            return (0,)

    update_available = _version_tuple(latest_tag) > _version_tuple(CURRENT_VERSION)
    return {
        "update_available": update_available,
        "current": CURRENT_VERSION,
        "latest": latest_tag,
        "latest_name": latest_name,
        "release_url": release_url,
        "published_at": published_at,
    }


@router.get("/recycling-bin")
async def recycling_bin_info(user=Depends(get_current_user)):
    """Return live recycling bin status and size."""
    recycle_path = _get_recycling_bin_path()
    if not recycle_path:
        return {
            "enabled": False,
            "path": "",
            "exists": False,
            "files": 0,
            "bytes": 0,
        }

    exists = os.path.isdir(recycle_path)
    files_count, total_bytes = _dir_stats(recycle_path) if exists else (0, 0)
    return {
        "enabled": True,
        "path": recycle_path,
        "exists": exists,
        "files": files_count,
        "bytes": total_bytes,
    }


@router.post("/recycling-bin/empty")
async def recycling_bin_empty(user=Depends(get_current_user)):
    """Delete all files/folders inside the configured recycling bin."""
    recycle_path = _get_recycling_bin_path()
    if not recycle_path:
        return {"status": "disabled", "removed_files": 0, "removed_dirs": 0, "freed_bytes": 0}

    if not os.path.isdir(recycle_path):
        return {"status": "not_found", "removed_files": 0, "removed_dirs": 0, "freed_bytes": 0}

    removed_files = 0
    removed_dirs = 0
    freed_bytes = 0

    for entry in os.scandir(recycle_path):
        try:
            if entry.is_file(follow_symlinks=False):
                try:
                    freed_bytes += os.path.getsize(entry.path)
                except OSError:
                    pass
                os.remove(entry.path)
                removed_files += 1
            elif entry.is_dir(follow_symlinks=False):
                files_count, bytes_count = _dir_stats(entry.path)
                shutil.rmtree(entry.path, ignore_errors=True)
                removed_dirs += 1
                removed_files += files_count
                freed_bytes += bytes_count
        except Exception:
            # Continue cleaning even if one entry fails
            continue

    return {
        "status": "emptied",
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "freed_bytes": freed_bytes,
    }


@router.get("/status")
async def get_system_status(user=Depends(get_current_user)):
    scheduler = get_scheduler()
    return {
        "cycle": get_status(),
        "scheduler_running": scheduler.running if scheduler else False,
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


async def _build_services_health() -> dict[str, Any]:
    """Quick connectivity check for all configured integrations."""
    from backend.config import get_config

    config = get_config()
    results: dict[str, Any] = {}

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

    # NZBGet
    # Username/password are optional in some installations; URL is the only hard requirement.
    if config.nzbget.url:
        try:
            from backend.integrations.nzbget import NZBGetClient
            results["nzbget"] = await NZBGetClient().test_connection()
        except Exception as e:
            results["nzbget"] = {"success": False, "error": str(e)}
    else:
        results["nzbget"] = {"success": False, "error": "Not configured"}

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


@router.get("/health/services")
async def services_health(user=Depends(get_current_user)):
    return await _build_services_health()


@router.get("/health/matrix")
async def health_matrix(user=Depends(get_current_user)):
    """Return end-to-end health for app, DB, scheduler, queue, and integrations."""
    components: dict[str, dict[str, Any]] = {
        "api": {"status": "healthy", "detail": "HTTP API reachable"},
    }

    try:
        async with async_session() as db:
            movies_total = (await db.execute(select(func.count()).select_from(Movie))).scalar_one()
            active_downloads = (
                await db.execute(
                    select(func.count()).select_from(Download).where(
                        Download.status.in_(["queued", "downloading", "processing"])
                    )
                )
            ).scalar_one()
        components["database"] = {
            "status": "healthy",
            "detail": "Connected",
            "movies_total": int(movies_total),
        }
        components["queue"] = {
            "status": "healthy",
            "detail": f"{int(active_downloads)} active downloads",
            "active_downloads": int(active_downloads),
        }
    except Exception as e:
        components["database"] = {"status": "down", "detail": str(e)}
        components["queue"] = {"status": "down", "detail": "Unavailable while database is down"}

    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        components["scheduler"] = {"status": "healthy", "detail": "Scheduler running"}
    elif scheduler:
        components["scheduler"] = {"status": "degraded", "detail": "Scheduler initialized but not running"}
    else:
        components["scheduler"] = {"status": "down", "detail": "Scheduler unavailable"}

    cycle = get_status()
    if cycle.get("running"):
        components["orchestrator"] = {"status": "healthy", "detail": "Cycle currently running"}
    elif cycle.get("stop_requested"):
        components["orchestrator"] = {"status": "degraded", "detail": "Stop requested"}
    else:
        components["orchestrator"] = {"status": "healthy", "detail": "Idle"}

    recycle_path = _get_recycling_bin_path()
    if not recycle_path:
        components["recycling_bin"] = {"status": "disabled", "detail": "Not configured"}
    elif os.path.isdir(recycle_path):
        files_count, bytes_count = _dir_stats(recycle_path)
        components["recycling_bin"] = {
            "status": "healthy",
            "detail": "Configured",
            "path": recycle_path,
            "files": files_count,
            "bytes": bytes_count,
        }
    else:
        components["recycling_bin"] = {
            "status": "degraded",
            "detail": "Configured path does not exist",
            "path": recycle_path,
        }

    integration_results = await _build_services_health()
    integration_summary = {"healthy": 0, "down": 0, "disabled": 0}
    for key, value in integration_results.items():
        if key == "indexers":
            continue
        success = bool(value.get("success")) if isinstance(value, dict) else False
        error = value.get("error") if isinstance(value, dict) else None
        if success:
            integration_summary["healthy"] += 1
        elif error in {"Disabled", "Not configured", "Missing URL or API key"}:
            integration_summary["disabled"] += 1
        else:
            integration_summary["down"] += 1

    components["integrations"] = {
        "status": "healthy" if integration_summary["down"] == 0 else "degraded",
        "detail": (
            f"{integration_summary['healthy']} healthy, "
            f"{integration_summary['down']} down, "
            f"{integration_summary['disabled']} disabled"
        ),
        "summary": integration_summary,
    }

    down_count = sum(1 for comp in components.values() if comp.get("status") == "down")
    degraded_count = sum(1 for comp in components.values() if comp.get("status") == "degraded")
    overall = "healthy"
    if down_count > 0:
        overall = "down"
    elif degraded_count > 0:
        overall = "degraded"

    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }


@router.get("/decision-audit")
async def decision_audit(limit: int = 50, decision: str = "", user=Depends(get_current_user)):
    """Return recent comparison decisions with rationale."""
    limit = max(1, min(limit, 500))
    query = select(DecisionAuditLog).order_by(DecisionAuditLog.created_at.desc()).limit(limit)
    normalized_decision = (decision or "").strip().lower()
    if normalized_decision in {"accept", "reject"}:
        query = (
            select(DecisionAuditLog)
            .where(DecisionAuditLog.decision == normalized_decision)
            .order_by(DecisionAuditLog.created_at.desc())
            .limit(limit)
        )

    async with async_session() as db:
        rows = (await db.execute(query)).scalars().all()

    return [
        {
            "id": row.id,
            "movie_id": row.movie_id,
            "movie_title": row.movie_title,
            "indexer_name": row.indexer_name,
            "release_title": row.release_title,
            "candidate_size": row.candidate_size,
            "local_size": row.local_size,
            "decision": row.decision,
            "score": row.score,
            "savings_bytes": row.savings_bytes,
            "savings_pct": row.savings_pct,
            "reject_reason": row.reject_reason,
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Self-update
# ---------------------------------------------------------------------------
_update_lock = False  # prevent concurrent updates


@router.post("/update")
async def trigger_update(background: BackgroundTasks, user=Depends(get_current_user)):
    """
    Pull latest code from GitHub, install new dependencies, then signal the
    watchdog (run.py) to restart the server by exiting with code 42.
    Progress is streamed to the frontend via Socket.IO events.
    """
    global _update_lock
    if _update_lock:
        return {"status": "already_running"}
    _update_lock = True
    background.add_task(_run_update)
    return {"status": "started"}


async def _run_update() -> None:
    global _update_lock
    import asyncio
    from loguru import logger
    from backend.realtime.events import emit_event

    async def _emit(line: str, level: str = "info") -> None:
        await emit_event("update:log", {"line": line, "level": level})
        logger.info(f"[update] {line}")

    try:
        # backend/api/system.py -> backend/api -> backend -> project root
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        python = sys.executable

        await _emit("Starting update...")

        # 1. git pull
        await _emit("Running git pull...")
        git_result = await asyncio.create_subprocess_exec(
            "git", "pull", "--ff-only",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in git_result.stdout:
            await _emit(raw.decode(errors="replace").rstrip())
        await git_result.wait()
        if git_result.returncode != 0:
            await _emit(f"git pull failed (exit {git_result.returncode})", "error")
            await emit_event("update:failed", {"reason": "git pull failed"})
            return

        # 2. pip install -r requirements.txt
        await _emit("Installing dependencies...")
        pip_result = await asyncio.create_subprocess_exec(
            python, "-m", "pip", "install", "-r", os.path.join(root, "requirements.txt"), "--quiet",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in pip_result.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                await _emit(line)
        await pip_result.wait()
        if pip_result.returncode != 0:
            await _emit(f"pip install failed (exit {pip_result.returncode})", "error")
            await emit_event("update:failed", {"reason": "pip install failed"})
            return

        await _emit("Update complete — restarting server...")
        await emit_event("update:restarting", {})
        # Give the WebSocket event time to reach the client before we exit
        await asyncio.sleep(1.5)
        # Signal the watchdog to restart (os._exit bypasses asyncio cleanup)
        os._exit(42)

    except Exception as e:
        await emit_event("update:failed", {"reason": str(e)})
        logger.error(f"Update failed: {e}")
    finally:
        _update_lock = False
