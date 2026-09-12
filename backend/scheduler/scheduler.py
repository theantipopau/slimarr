"""APScheduler configuration — nightly, continuous interval, and cleanup jobs."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from backend.core.schedule_window import get_schedule_timezone, is_within_schedule_window, parse_schedule_time

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def _time_after_window_end(config, *, offset_minutes: int) -> tuple[int, int]:
    """A clock time `offset_minutes` after the configured nightly window
    closes, for scheduling auxiliary cleanup jobs so they never overlap the
    nightly cycle's own I/O (see start_scheduler)."""
    end_t = parse_schedule_time(config.schedule.end_time, "07:00")
    anchor = datetime(2000, 1, 1, end_t.hour, end_t.minute) + timedelta(minutes=offset_minutes)
    return anchor.hour, anchor.minute


async def _nightly_cycle() -> None:
    from backend.config import get_config
    from backend.core.orchestrator import run_full_cycle

    config = get_config()
    if not is_within_schedule_window(config):
        logger.info("Nightly cycle skipped (outside configured schedule window)")
        return

    logger.info("Nightly cycle triggered")
    await run_full_cycle()


async def _cleanup_recycle_bin() -> None:
    """Remove files from recycle bin older than configured days."""
    import os
    import time
    from backend.config import get_config
    from backend.core.storage import remove_path

    config = get_config()
    recycle_dir = config.files.recycling_bin
    max_age_days = config.files.recycling_bin_cleanup_days

    if not recycle_dir or not os.path.isdir(recycle_dir):
        return

    cutoff = time.time() - max_age_days * 86400
    removed = 0

    def _expired_files() -> list[tuple[str, int]]:
        expired: list[tuple[str, int]] = []
        with os.scandir(recycle_dir) as entries:
            for entry in entries:
                try:
                    stat = entry.stat(follow_symlinks=False)
                    if entry.is_file(follow_symlinks=False) and stat.st_mtime < cutoff:
                        expired.append((entry.path, int(stat.st_size)))
                except OSError:
                    continue
        return expired

    for fpath, file_size in await asyncio.to_thread(_expired_files):
        try:
            await remove_path(
                fpath,
                config,
                purpose="scheduled_recycling_cleanup",
                estimated_bytes=file_size,
            )
            removed += 1
        except Exception as e:
            logger.warning(f"Failed to remove recycled file {fpath}: {e}")

    if removed:
        logger.info(f"Cleaned {removed} file(s) from recycle bin")


async def _orphan_scanner() -> None:
    from backend.core.orphan_scanner import auto_cleanup_old_orphans, scan_orphaned_downloads

    logger.info("Orphan scanner triggered")
    found = await scan_orphaned_downloads()
    if found:
        logger.info(f"Orphan scanner found {found} new orphaned download(s)")

    cleaned = await auto_cleanup_old_orphans(days_old=7)
    if cleaned:
        logger.info(f"Orphan auto-cleanup removed {cleaned} old orphan record(s)")


async def _downloader_health_pulse() -> None:
    from backend.integrations.download_client import get_active_download_client_name, get_download_client

    client_name = get_active_download_client_name()
    client = get_download_client(client_name)
    try:
        health = await client.test_connection()
        if not health.get("success"):
            logger.warning(f"Downloader health pulse failed for {client_name}: {health.get('error', 'unknown')}")
        else:
            logger.debug(f"Downloader health pulse OK for {client_name}")
    except Exception as exc:
        logger.warning(f"Downloader health pulse exception for {client_name}: {exc}")


async def _stale_download_recovery() -> None:
    from backend.core.download_workflow import resume_downloading_downloads

    resumed = await resume_downloading_downloads(limit=100)
    if resumed:
        logger.info(f"Stale download recovery resumed {resumed} workflow(s)")


async def _telemetry_retention_cleanup() -> None:
    """Purge old terminal job records and persisted storage operation logs."""
    from backend.core.jobs import purge_old_jobs
    from backend.core.storage import purge_old_storage_operations

    jobs_removed = await purge_old_jobs(keep_days=30)
    ops_removed = await purge_old_storage_operations(keep_days=30)
    if jobs_removed or ops_removed:
        logger.info(
            "Telemetry retention: removed {} job record(s) and {} storage operation record(s)",
            jobs_removed,
            ops_removed,
        )


def start_scheduler() -> None:
    from backend.config import get_config
    config = get_config()

    scheduler = get_scheduler()
    scheduler.configure(timezone=get_schedule_timezone(config))

    # Window start trigger — use schedule.start_time (for example "23:00")
    nightly_time = config.schedule.start_time
    try:
        hour, minute = nightly_time.split(":", 1)
    except Exception:
        hour, minute = "23", "0"

    scheduler.add_job(
        _nightly_cycle,
        CronTrigger(hour=int(hour), minute=int(minute)),
        id="night_window_start_cycle",
        replace_existing=True,
    )

    scheduler.add_job(
        _nightly_cycle,
        IntervalTrigger(hours=1),
        id="night_window_pulse",
        replace_existing=True,
    )
    logger.info(
        f"Scheduled nightly cycle window {config.schedule.start_time} -> {config.schedule.end_time} ({get_schedule_timezone(config)})"
    )

    # Recycle bin cleanup and orphan scanning both do their own filesystem
    # I/O (deleting recycled files, stat-ing/removing orphaned download
    # folders) and used to run at fixed clock times (03:00/04:00) regardless
    # of the configured nightly window - for the *default* window
    # (01:00 -> 07:00), and for most real configurations, that lands
    # squarely in the middle of the nightly cycle's own replacement I/O,
    # stacking concurrent NAS load right when it's least wanted. Scheduling
    # them a short while after the window closes instead means they only
    # ever run once the heavier nightly work has finished.
    recycle_hour, recycle_minute = _time_after_window_end(config, offset_minutes=15)
    scheduler.add_job(
        _cleanup_recycle_bin,
        CronTrigger(hour=recycle_hour, minute=recycle_minute),
        id="recycle_cleanup",
        replace_existing=True,
    )

    orphan_hour, orphan_minute = _time_after_window_end(config, offset_minutes=30)
    scheduler.add_job(
        _orphan_scanner,
        CronTrigger(hour=orphan_hour, minute=orphan_minute),
        id="orphan_scanner",
        replace_existing=True,
    )

    # Downloader health pulse — every 30 minutes
    scheduler.add_job(
        _downloader_health_pulse,
        IntervalTrigger(minutes=30),
        id="downloader_health_pulse",
        replace_existing=True,
    )

    # Stale download recovery - expires old stuck jobs and restarts missing monitor tasks.
    scheduler.add_job(
        _stale_download_recovery,
        IntervalTrigger(hours=1),
        id="stale_download_recovery",
        replace_existing=True,
    )

    # Telemetry retention — daily at 05:00, removes terminal job and storage-op records older than 30 days.
    scheduler.add_job(
        _telemetry_retention_cleanup,
        CronTrigger(hour=5, minute=0),
        id="telemetry_retention_cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def list_jobs() -> list[dict]:
    scheduler = get_scheduler()
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        jobs.append({"id": job.id, "name": job.name, "next_run": next_run})
    return jobs
