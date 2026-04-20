"""APScheduler configuration — nightly, continuous interval, and cleanup jobs."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def _nightly_cycle() -> None:
    from backend.core.orchestrator import run_full_cycle
    logger.info("Nightly cycle triggered")
    await run_full_cycle()


async def _cleanup_recycle_bin() -> None:
    """Remove files from recycle bin older than configured days."""
    import os
    import time
    from backend.config import get_config

    config = get_config()
    recycle_dir = config.files.recycling_bin
    max_age_days = config.files.recycling_bin_cleanup_days

    if not recycle_dir or not os.path.isdir(recycle_dir):
        return

    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for fname in os.listdir(recycle_dir):
        fpath = os.path.join(recycle_dir, fname)
        if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
            try:
                os.remove(fpath)
                removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove recycled file {fpath}: {e}")

    if removed:
        logger.info(f"Cleaned {removed} file(s) from recycle bin")


def start_scheduler() -> None:
    from backend.config import get_config
    config = get_config()

    scheduler = get_scheduler()

    # Nightly cycle — use schedule.start_time ("01:00")
    nightly_time = config.schedule.start_time
    try:
        hour, minute = nightly_time.split(":")
    except Exception:
        hour, minute = "1", "0"

    scheduler.add_job(
        _nightly_cycle,
        CronTrigger(hour=int(hour), minute=int(minute)),
        id="nightly_cycle",
        replace_existing=True,
    )
    logger.info(f"Scheduled nightly cycle at {nightly_time} UTC")

    # Recycle bin cleanup — daily at 03:00
    scheduler.add_job(
        _cleanup_recycle_bin,
        CronTrigger(hour=3, minute=0),
        id="recycle_cleanup",
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
