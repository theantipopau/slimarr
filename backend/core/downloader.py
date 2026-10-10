"""
Download manager — sends NZB URLs to the active downloader and polls for completion.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.utils.clock import utc_now
from backend.config import get_config
from backend.core.storage import remove_path
from backend.database import Download, Movie, SearchResult, UploaderStats, async_session
from backend.integrations.download_client import decode_job_id, encode_job_id, get_active_download_client_name, get_download_client
from backend.core.parser import parse_release_title
from backend.core.search_diagnostics import redact_text
from backend.realtime.events import emit_event

TRANSIENT_HISTORY_STATUSES = {
    "checking",
    "downloading",
    "extracting",
    "fetching",
    "queued",
    "quickcheck",
    "repairing",
    "running",
    "verifying",
}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _active_download_age_hours(dl: Download) -> float | None:
    started_at = _as_utc(dl.started_at)
    if not started_at:
        return None
    return (utc_now() - started_at).total_seconds() / 3600


def _max_active_download_hours() -> int:
    config = get_config()
    return max(1, int(getattr(config.schedule, "max_active_download_hours", 24) or 24))


def _mark_download_failed(
    dl: Download,
    message: str,
    *,
    storage_path: str | None = None,
) -> None:
    dl.status = "failed"
    dl.error_message = message
    dl.last_error_at = utc_now()
    dl.completed_at = utc_now()
    if storage_path is not None:
        dl.storage_path = storage_path


async def _update_uploader_stats(release_title: str | None, success: bool) -> None:
    if not release_title:
        return

    parsed = parse_release_title(release_title)
    uploader = parsed.uploader or parsed.group
    if not uploader:
        return

    async with async_session() as db:
        result = await db.execute(select(UploaderStats).where(UploaderStats.uploader == uploader))
        stats = result.scalar_one_or_none()
        if not stats:
            stats = UploaderStats(uploader=uploader)
            db.add(stats)

        if success:
            stats.success_count = int(stats.success_count or 0) + 1
        else:
            stats.failure_count = int(stats.failure_count or 0) + 1

        total = int(stats.success_count or 0) + int(stats.failure_count or 0) + int(stats.corruption_count or 0)
        if total > 0:
            success_count = float(stats.success_count or 0)
            stats.health_score = max(0.0, min(1.0, success_count / float(total)))
        stats.last_seen = utc_now()
        await db.commit()


async def get_uploader_health_scores(uploaders: list[str]) -> dict[str, float]:
    """Batched uploader-health lookup for a whole search's candidates in one
    query, via the normal async engine (works on SQLite and PostgreSQL alike).

    Replaces per-candidate synchronous sqlite3 lookups in the comparer, which
    ran on the event loop thread once per candidate (dozens to 100+ times per
    movie search) and silently returned the 0.5 default for every uploader on
    a PostgreSQL backend.
    """
    unique_uploaders = sorted({u for u in uploaders if u})
    if not unique_uploaders:
        return {}

    async with async_session() as db:
        result = await db.execute(
            select(UploaderStats.uploader, UploaderStats.health_score).where(
                UploaderStats.uploader.in_(unique_uploaders)
            )
        )
        return {
            uploader: max(0.0, min(1.0, float(score)))
            for uploader, score in result.all()
            if score is not None
        }


async def start_download(search_result_id: int) -> Download:
    """Submit a search result to the active downloader. Returns the Download row."""
    config = get_config()
    if config.automation.dry_run:
        raise RuntimeError("Dry-run mode is enabled; downloads are disabled")

    client_name = get_active_download_client_name()
    client = get_download_client(client_name)

    async with async_session() as db:
        sr_result = await db.execute(
            select(SearchResult).where(SearchResult.id == search_result_id)
        )
        sr = sr_result.scalar_one_or_none()
        if not sr:
            raise ValueError(f"SearchResult {search_result_id} not found")

        movie_result = await db.execute(select(Movie).where(Movie.id == sr.movie_id))
        movie = movie_result.scalar_one_or_none()
        if not movie:
            raise ValueError(f"Movie {sr.movie_id} not found")

        dl = Download(
            movie_id=movie.id,
            search_result_id=sr.id,
            nzo_id=None,
            release_title=sr.release_title,
            expected_size=sr.size,
            status="submitting",
            progress_pct=0.0,
            started_at=utc_now(),
        )
        db.add(dl)
        movie.status = "downloading"
        await db.commit()
        await db.refresh(dl)

        try:
            external_job_id = await client.submit_url(sr.nzb_url, sr.release_title)
        except Exception as exc:
            _mark_download_failed(dl, f"{client_name} submit failed: {redact_text(str(exc))}")
            movie.status = "failed"
            movie.error_message = dl.error_message
            await db.commit()
            await emit_event("download:failed", {
                "download_id": dl.id,
                "movie_id": movie.id,
                "reason": dl.error_message,
            })
            raise
        stored_job_id = encode_job_id(client_name, external_job_id)
        logger.info(
            f"Submitted to {client_name}: {sr.release_title} → job_id={external_job_id}"
        )

        dl.nzo_id = stored_job_id
        dl.status = "downloading"
        await db.commit()
        await db.refresh(dl)

        await emit_event("download:started", {
            "movie_id": movie.id,
            "title": movie.title,
            "nzo_id": stored_job_id,
            "download_client": client_name,
            "release_title": sr.release_title,
        })
        return dl


async def monitor_download(download_id: int, poll_interval: int = 5) -> str:
    """
    Poll the stored download client until the download completes or fails.
    Returns final status: "completed" | "failed" | "missing"
    """
    consecutive_none = 0  # count polls where job is not found at all
    consecutive_poll_errors = 0  # count polls where the client call itself raised
    MAX_NONE_RETRIES = 6  # ~30s of grace before giving up
    max_active_hours = _max_active_download_hours()

    while True:
        await asyncio.sleep(poll_interval)

        async with async_session() as db:
            dl_result = await db.execute(select(Download).where(Download.id == download_id))
            dl = dl_result.scalar_one_or_none()
            if not dl:
                return "missing"

            age_hours = _active_download_age_hours(dl)
            if age_hours is not None and age_hours >= max_active_hours:
                reason = (
                    f"Download exceeded active timeout "
                    f"({age_hours:.1f}h >= {max_active_hours}h)"
                )
                logger.warning(f"Download {download_id}: {reason}")
                _mark_download_failed(dl, reason)
                await db.commit()
                await _update_uploader_stats(dl.release_title, success=False)
                await emit_event("download:failed", {
                    "download_id": dl.id,
                    "movie_id": dl.movie_id,
                    "reason": dl.error_message,
                })
                return "failed"

            client_name, external_job_id = decode_job_id(dl.nzo_id)
            client = get_download_client(client_name)

            try:
                status = await client.get_job_status(external_job_id)
                consecutive_poll_errors = 0
            except Exception as e:
                consecutive_poll_errors += 1
                # If the client is genuinely down, this poll runs every
                # `poll_interval` seconds forever — log the first failure at
                # warning so it's visible, then back off to a periodic
                # reminder instead of repeating the identical line every poll.
                if consecutive_poll_errors == 1 or consecutive_poll_errors % 12 == 0:
                    logger.warning(
                        "{} poll error for download {} (consecutive failures: {}): {}",
                        client_name,
                        download_id,
                        consecutive_poll_errors,
                        redact_text(str(e)),
                    )
                continue

            if status is None:
                consecutive_none += 1
                logger.warning(
                    f"Download {download_id}: job not found in {client_name} queue or history "
                    f"(attempt {consecutive_none}/{MAX_NONE_RETRIES})"
                )
                if consecutive_none < MAX_NONE_RETRIES:
                    continue

                logger.error(
                    f"Download {download_id}: marking as failed — job not found in {client_name} "
                    f"after {MAX_NONE_RETRIES} retries (progress was {dl.progress_pct or 0:.0f}%)"
                )
                _mark_download_failed(dl, f"Job not found in {client_name} history/queue")
                await db.commit()
                await _update_uploader_stats(dl.release_title, success=False)
                await emit_event("download:failed", {
                    "download_id": dl.id,
                    "movie_id": dl.movie_id,
                    "reason": dl.error_message,
                })
                return "failed"
            else:
                consecutive_none = 0  # reset on any successful status response

            location = status.get("location", "queue")

            if location == "queue":
                pct = float(status.get("percentage", 0) or 0)
                dl.progress_pct = pct
                await db.commit()
                await emit_event("download:progress", {
                    "download_id": dl.id,
                    "movie_id": dl.movie_id,
                    "progress_pct": pct,
                    "status": status.get("status", ""),
                    "speed": status.get("speed", ""),
                    "timeleft": status.get("timeleft", ""),
                    "download_client": client_name,
                })

            elif location == "history":
                raw_status = str(status.get("status", ""))
                normalized_status = raw_status.lower()
                dl.storage_path = status.get("storage", "")
                logger.info(
                    f"Download {download_id}: found in {client_name} history — "
                    f"status={normalized_status!r} storage={dl.storage_path!r}"
                )

                is_success = normalized_status in ("completed", "repaired") or normalized_status.startswith("success") or normalized_status.startswith("warning")
                if normalized_status in TRANSIENT_HISTORY_STATUSES:
                    await db.commit()
                    logger.info(
                        f"Download {download_id}: {client_name} history status "
                        f"{normalized_status!r} is still post-processing; continuing monitor"
                    )
                    continue

                if is_success:
                    if not dl.storage_path:
                        _mark_download_failed(dl, f"{client_name} completed job has no storage path")
                        await db.commit()
                        await _update_uploader_stats(dl.release_title, success=False)
                        await emit_event("download:failed", {
                            "download_id": dl.id,
                            "movie_id": dl.movie_id,
                            "reason": dl.error_message,
                        })
                        return "failed"
                    dl.status = "completed"
                    dl.progress_pct = 100.0
                    dl.completed_at = utc_now()
                    await db.commit()
                    await _update_uploader_stats(dl.release_title, success=True)
                    await emit_event("download:completed", {
                        "download_id": dl.id,
                        "movie_id": dl.movie_id,
                        "storage": dl.storage_path,
                    })
                    return "completed"
                else:
                    fail_message = status.get("fail_message") or raw_status
                    _mark_download_failed(
                        dl,
                        f"{client_name} status: {fail_message}",
                        storage_path=status.get("storage", ""),
                    )
                    await db.commit()
                    await _update_uploader_stats(dl.release_title, success=False)
                    await emit_event("download:failed", {
                        "download_id": dl.id,
                        "movie_id": dl.movie_id,
                        "reason": dl.error_message,
                    })
                    return "failed"


async def cleanup_failed_download(download_id: int) -> dict:
    """
    Attempt to delete storage folder and remove job from downloader history.
    Returns: {
        "status": "cleaned" | "error" | "skipped",
        "folder_deleted": bool,
        "downloader_purged": bool,
        "error_reason": str | None,
    }
    """
    async with async_session() as db:
        dl_result = await db.execute(select(Download).where(Download.id == download_id))
        dl = dl_result.scalar_one_or_none()
        if not dl:
            return {"status": "skipped", "reason": "download not found"}

        if dl.status != "failed":
            return {"status": "skipped", "reason": f"download status is {dl.status}, not failed"}

        client_name, external_job_id = decode_job_id(dl.nzo_id)
        client = get_download_client(client_name)

        # Step 1: Try to remove from downloader
        downloader_purged = False
        if external_job_id:
            downloader_purged = await client.purge_job(external_job_id)

        # Step 2: Try to delete storage folder
        folder_deleted = False
        if dl.storage_path:
            try:
                result = await remove_path(
                    dl.storage_path,
                    get_config(),
                    purpose="failed_download_cleanup",
                    recursive=True,
                )
                folder_deleted = result.status in {"completed", "skipped"}
                logger.info(
                    f"Cleaned up failed download path: {dl.storage_path} ({result.status})"
                )
            except Exception as e:
                logger.warning(f"Failed to delete {dl.storage_path}: {e}")

        # Mark cleanup attempt
        cleanup_status = "cleaned" if (folder_deleted or downloader_purged) else "error"
        dl.cleanup_status = cleanup_status
        await db.commit()

        await emit_event("download:cleanup", {
            "download_id": dl.id,
            "folder_deleted": folder_deleted,
            "downloader_purged": downloader_purged,
        })

        return {
            "status": cleanup_status,
            "folder_deleted": folder_deleted,
            "downloader_purged": downloader_purged,
        }
