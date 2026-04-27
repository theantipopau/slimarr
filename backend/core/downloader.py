"""
Download manager — sends NZB URLs to the active downloader and polls for completion.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.database import Download, Movie, SearchResult, async_session
from backend.integrations.download_client import decode_job_id, encode_job_id, get_active_download_client_name, get_download_client
from backend.realtime.events import emit_event


async def start_download(search_result_id: int) -> Download:
    """Submit a search result to the active downloader. Returns the Download row."""
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

        external_job_id = await client.submit_url(sr.nzb_url, sr.release_title)
        stored_job_id = encode_job_id(client_name, external_job_id)
        logger.info(
            f"Submitted to {client_name}: {sr.release_title} → job_id={external_job_id}"
        )

        dl = Download(
            movie_id=movie.id,
            search_result_id=sr.id,
            nzo_id=stored_job_id,
            release_title=sr.release_title,
            expected_size=sr.size,
            status="downloading",
            progress_pct=0.0,
            started_at=datetime.now(timezone.utc),
        )
        db.add(dl)
        movie.status = "downloading"
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
    MAX_NONE_RETRIES = 6  # ~30s of grace before giving up

    while True:
        await asyncio.sleep(poll_interval)

        async with async_session() as db:
            dl_result = await db.execute(select(Download).where(Download.id == download_id))
            dl = dl_result.scalar_one_or_none()
            if not dl:
                return "missing"

            client_name, external_job_id = decode_job_id(dl.nzo_id)
            client = get_download_client(client_name)

            try:
                status = await client.get_job_status(external_job_id)
            except Exception as e:
                logger.warning(f"{client_name} poll error for download {download_id}: {e}")
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
                dl.status = "failed"
                dl.error_message = f"Job not found in {client_name} history/queue"
                await db.commit()
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
                if is_success:
                    if not dl.storage_path:
                        dl.status = "failed"
                        dl.error_message = f"{client_name} completed job has no storage path"
                        await db.commit()
                        await emit_event("download:failed", {
                            "download_id": dl.id,
                            "movie_id": dl.movie_id,
                            "reason": dl.error_message,
                        })
                        return "failed"
                    dl.status = "completed"
                    dl.progress_pct = 100.0
                    dl.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    await emit_event("download:completed", {
                        "download_id": dl.id,
                        "movie_id": dl.movie_id,
                        "storage": dl.storage_path,
                    })
                    return "completed"
                else:
                    dl.status = "failed"
                    dl.error_message = f"{client_name} status: {raw_status}"
                    await db.commit()
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
    import os
    import shutil

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
        downloader_purged = await client.purge_job(external_job_id)

        # Step 2: Try to delete storage folder
        folder_deleted = False
        if dl.storage_path:
            try:
                if os.path.isdir(dl.storage_path):
                    shutil.rmtree(dl.storage_path, ignore_errors=True)
                    logger.info(f"Cleaned up failed download folder: {dl.storage_path}")
                    folder_deleted = True
                elif os.path.isfile(dl.storage_path):
                    os.remove(dl.storage_path)
                    logger.info(f"Cleaned up failed download file: {dl.storage_path}")
                    folder_deleted = True
            except Exception as e:
                logger.warning(f"Failed to delete {dl.storage_path}: {e}")

        # Mark cleanup attempt
        dl.cleanup_status = "cleaned" if (folder_deleted or downloader_purged) else "error"
        await db.commit()

        await emit_event("download:cleanup", {
            "download_id": dl.id,
            "folder_deleted": folder_deleted,
            "downloader_purged": downloader_purged,
        })

        return {
            "status": "cleaned",
            "folder_deleted": folder_deleted,
            "downloader_purged": downloader_purged,
        }
