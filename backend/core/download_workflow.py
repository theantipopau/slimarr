"""Shared download workflow: monitor, replace, cleanup, and retry."""
from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.downloader import (
    _mark_download_failed,
    _max_active_download_hours,
    cleanup_failed_download,
    monitor_download,
    start_download,
)
from backend.core.replacer import replace_file
from backend.core.retry_ladder import retry_failed_download
from backend.database import Download, Movie, async_session

_active_workflows: set[int] = set()


async def process_search_result_download(search_result_id: int) -> dict:
    """Start a download and drive it through replacement or retry exhaustion."""
    dl = await start_download(search_result_id)
    return await finish_download_with_retries(dl.id)


async def finish_download_with_retries(download_id: int) -> dict:
    """Monitor one download, replacing on success and retrying alternatives on failure."""
    if download_id in _active_workflows:
        return {"status": "already_monitoring", "download_id": download_id}

    _active_workflows.add(download_id)
    try:
        return await _finish_download_with_retries(download_id)
    finally:
        _active_workflows.discard(download_id)


async def resume_downloading_downloads(limit: int = 50) -> int:
    """Resume monitor workflows for downloads left active across restarts."""
    import asyncio

    expired_ids = await expire_stale_active_downloads()

    async with async_session() as session:
        result = await session.execute(
            select(Download.id)
            .where(Download.status == "downloading")
            .order_by(Download.started_at.asc())
            .limit(limit)
        )
        active_ids = list(result.scalars().all())

    download_ids = [
        row for row in [*expired_ids, *active_ids]
        if row not in _active_workflows
    ][:limit]

    for active_download_id in download_ids:
        logger.info(f"Resuming monitor workflow for download {active_download_id}")
        asyncio.create_task(finish_download_with_retries(active_download_id))

    return len(download_ids)


async def expire_stale_active_downloads() -> list[int]:
    """Mark old active downloads as failed so retry handling can continue."""
    max_hours = _max_active_download_hours()
    now = datetime.now(timezone.utc)
    expired_ids: list[int] = []

    async with async_session() as session:
        result = await session.execute(
            select(Download, Movie)
            .join(Movie, Movie.id == Download.movie_id)
            .where(Download.status.in_(["submitting", "downloading"]))
        )
        for download, movie in result.all():
            started_at = download.started_at
            if started_at is None:
                continue
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            age_hours = (now - started_at.astimezone(timezone.utc)).total_seconds() / 3600
            if age_hours < max_hours:
                continue

            reason = (
                f"Download exceeded active timeout "
                f"({age_hours:.1f}h >= {max_hours}h)"
            )
            _mark_download_failed(download, reason)
            movie.status = "failed"
            movie.error_message = reason
            expired_ids.append(download.id)
            logger.warning(f"Expired stale download {download.id}: {reason}")

        if expired_ids:
            await session.commit()

    return expired_ids


async def _finish_download_with_retries(download_id: int) -> dict:
    current_download_id = download_id

    while True:
        current_status = await _get_download_status(current_download_id)
        final_status = "failed" if current_status == "failed" else await monitor_download(current_download_id)

        if final_status == "completed":
            replaced = await replace_file(current_download_id)
            if not replaced:
                await _mark_movie_failed(current_download_id, "Replacement failed after completed download")
            return {
                "status": "replaced" if replaced else "replace_failed",
                "download_id": current_download_id,
            }

        if final_status != "failed":
            await _mark_movie_failed(current_download_id, f"Download ended with status: {final_status}")
            return {"status": f"download_{final_status}", "download_id": current_download_id}

        cleanup_result = await cleanup_failed_download(current_download_id)
        logger.info(
            f"Failed download cleanup for {current_download_id}: "
            f"{cleanup_result.get('status')} "
            f"folder_deleted={cleanup_result.get('folder_deleted')} "
            f"downloader_purged={cleanup_result.get('downloader_purged')}"
        )

        success, message, retried_download_id = await retry_failed_download(current_download_id)
        if not success or not retried_download_id:
            await _mark_movie_failed(current_download_id, message or "No retry candidate available")
            return {
                "status": "download_failed",
                "download_id": current_download_id,
                "message": message,
                "cleanup": cleanup_result,
            }

        logger.info(
            f"Retrying failed download {current_download_id} "
            f"as download {retried_download_id}: {message}"
        )
        current_download_id = retried_download_id


async def _get_download_status(download_id: int) -> str | None:
    async with async_session() as session:
        result = await session.execute(select(Download.status).where(Download.id == download_id))
        return result.scalar_one_or_none()


async def _mark_movie_failed(download_id: int, message: str) -> None:
    async with async_session() as session:
        result = await session.execute(select(Download).where(Download.id == download_id))
        download = result.scalar_one_or_none()
        if not download:
            return

        movie_result = await session.execute(select(Movie).where(Movie.id == download.movie_id))
        movie = movie_result.scalar_one_or_none()
        if not movie:
            return

        movie.status = "failed"
        movie.error_message = message
        await session.commit()
