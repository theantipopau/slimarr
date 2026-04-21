"""
Download manager — sends NZBs to SABnzbd and polls for completion.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.database import Download, Movie, SearchResult, async_session
from backend.realtime.events import emit_event


async def start_download(search_result_id: int) -> Download:
    """Submit a search result to SABnzbd. Returns the Download row."""
    from backend.integrations.sabnzbd import SABnzbdClient

    sab = SABnzbdClient()

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

        nzo_id = await sab.add_nzb_url(sr.nzb_url, sr.release_title)
        logger.info(f"Submitted to SABnzbd: {sr.release_title} → nzo_id={nzo_id}")

        dl = Download(
            movie_id=movie.id,
            search_result_id=sr.id,
            nzo_id=nzo_id,
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
            "nzo_id": nzo_id,
            "release_title": sr.release_title,
        })
        return dl


async def monitor_download(download_id: int, poll_interval: int = 5) -> str:
    """
    Poll SABnzbd until the download completes or fails.
    Returns final status: "completed" | "failed" | "missing"
    """
    from backend.integrations.sabnzbd import SABnzbdClient

    sab = SABnzbdClient()
    consecutive_none = 0  # count polls where job is not found at all
    MAX_NONE_RETRIES = 6  # ~30s of grace before giving up

    while True:
        await asyncio.sleep(poll_interval)

        async with async_session() as db:
            dl_result = await db.execute(select(Download).where(Download.id == download_id))
            dl = dl_result.scalar_one_or_none()
            if not dl:
                return "missing"

            try:
                status = await sab.get_job_status(dl.nzo_id)
            except Exception as e:
                logger.warning(f"SABnzbd poll error for download {download_id}: {e}")
                continue

            if status is None:
                consecutive_none += 1
                logger.warning(
                    f"Download {download_id}: job not found in SABnzbd queue or history "
                    f"(attempt {consecutive_none}/{MAX_NONE_RETRIES})"
                )
                if consecutive_none < MAX_NONE_RETRIES:
                    # Race condition: job may be moving from queue to history — retry
                    continue
                # Exhausted retries
                if dl.progress_pct and dl.progress_pct >= 50:
                    logger.warning(
                        f"Download {download_id}: marking as completed based on "
                        f"{dl.progress_pct:.0f}% progress (job disappeared from SABnzbd)"
                    )
                    dl.status = "completed"
                else:
                    logger.error(
                        f"Download {download_id}: marking as failed — job not found in SABnzbd "
                        f"after {MAX_NONE_RETRIES} retries (progress was {dl.progress_pct or 0:.0f}%)"
                    )
                    dl.status = "failed"
                    dl.error_message = "Job not found in SABnzbd"
                await db.commit()
                await emit_event(
                    "download:failed" if dl.status == "failed" else "download:completed",
                    {"download_id": dl.id, "movie_id": dl.movie_id},
                )
                return dl.status
            else:
                consecutive_none = 0  # reset on any successful status response

            location = status.get("location", "queue")

            if location == "queue":
                pct = float(status.get("percentage", 0))
                dl.progress_pct = pct
                await db.commit()
                await emit_event("download:progress", {
                    "download_id": dl.id,
                    "movie_id": dl.movie_id,
                    "progress_pct": pct,
                    "status": status.get("status", ""),
                    "speed": status.get("speed", ""),
                    "timeleft": status.get("timeleft", ""),
                })

            elif location == "history":
                sab_status = status.get("status", "").lower()
                dl.storage_path = status.get("storage", "")
                logger.info(
                    f"Download {download_id}: found in SABnzbd history — "
                    f"sab_status={sab_status!r} storage={dl.storage_path!r}"
                )

                if sab_status in ("completed", "repaired"):
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
                    dl.error_message = f"SABnzbd status: {sab_status}"
                    await db.commit()
                    await emit_event("download:failed", {
                        "download_id": dl.id,
                        "movie_id": dl.movie_id,
                        "reason": dl.error_message,
                    })
                    return "failed"
