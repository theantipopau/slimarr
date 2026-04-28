"""Shared download workflow: monitor, replace, cleanup, and retry."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from backend.core.downloader import cleanup_failed_download, monitor_download, start_download
from backend.core.replacer import replace_file
from backend.core.retry_ladder import retry_failed_download
from backend.database import Download, Movie, async_session


async def process_search_result_download(search_result_id: int) -> dict:
    """Start a download and drive it through replacement or retry exhaustion."""
    dl = await start_download(search_result_id)
    return await finish_download_with_retries(dl.id)


async def finish_download_with_retries(download_id: int) -> dict:
    """Monitor one download, replacing on success and retrying alternatives on failure."""
    current_download_id = download_id

    while True:
        final_status = await monitor_download(current_download_id)

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
