"""
File replacer — moves the downloaded file into place and refreshes Plex.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.database import ActivityLog, Download, Movie, async_session
from backend.realtime.events import emit_event

SUPPORTED_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v"}


def _find_video_file(directory: str) -> str | None:
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                return os.path.join(root, f)
    return None


async def replace_file(download_id: int) -> bool:
    """
    Move the downloaded file to the library, remove the old file,
    refresh Plex. Returns True on success.
    """
    from backend.config import get_config
    from backend.integrations.plex import PlexClient

    config = get_config()

    async with async_session() as db:
        dl_result = await db.execute(select(Download).where(Download.id == download_id))
        dl = dl_result.scalar_one_or_none()
        if not dl:
            raise ValueError(f"Download {download_id} not found")

        movie_result = await db.execute(select(Movie).where(Movie.id == dl.movie_id))
        movie = movie_result.scalar_one_or_none()
        if not movie:
            raise ValueError(f"Movie {dl.movie_id} not found")

        storage_path = dl.storage_path
        if not storage_path or not os.path.exists(storage_path):
            err = f"Downloaded storage path missing: {storage_path}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            return False

        # Find the actual video file inside the SABnzbd completed folder
        video_file = _find_video_file(storage_path) if os.path.isdir(storage_path) else storage_path
        if not video_file:
            err = f"No video file found in {storage_path}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            return False

        original_path = movie.file_path
        if not original_path:
            err = "Original file path unknown — cannot replace"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            return False

        # Target path calculation
        target_dir = os.path.dirname(original_path)
        ext = os.path.splitext(video_file)[1]
        target_path = os.path.splitext(original_path)[0] + ext

        # Recycle bin step: move original to recycle directory (if configured)
        recycle_dir = config.files.recycling_bin
        recycled_successfully = False
        if recycle_dir:
            os.makedirs(recycle_dir, exist_ok=True)
            # Include the parent folder name to avoid name collisions in the bin
            # e.g.  /recycle/MovieFolderName_movie.mkv
            folder_name = os.path.basename(os.path.dirname(original_path))
            base_name = os.path.basename(original_path)
            recycled_name = f"{folder_name}_{base_name}" if folder_name else base_name
            recycled_path = os.path.join(recycle_dir, recycled_name)
            try:
                shutil.move(original_path, recycled_path)
                logger.info(f"Moved original to recycle bin: {recycled_path}")
                recycled_successfully = True
            except Exception as e:
                logger.warning(f"Recycle move failed (continuing): {e}")

        # Move new file into place
        os.makedirs(target_dir, exist_ok=True)
        try:
            shutil.move(video_file, target_path)
        except Exception as e:
            err = f"File move failed: {e}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            return False

        logger.info(f"Replaced: {original_path} → {target_path}")

        # If not recycled and extensions differ, we must explicitly delete the old file
        if not recycled_successfully and original_path != target_path and os.path.exists(original_path):
            try:
                os.remove(original_path)
                logger.info(f"Deleted old file: {original_path}")
            except Exception as e:
                logger.warning(f"Failed to delete old file: {e}")

        # Update movie record
        new_size = os.path.getsize(target_path)
        if movie.original_file_size is None:
            movie.original_file_size = movie.file_size
        movie.file_path = target_path
        movie.file_size = new_size
        movie.status = "improved"

        # Update download record
        dl.status = "replaced"
        dl.completed_at = datetime.now(timezone.utc)

        # Log activity
        savings_bytes = (movie.original_file_size or 0) - new_size
        log = ActivityLog(
            movie_id=movie.id,
            movie_title=movie.title,
            event="replace:completed",
            old_file_path=original_path,
            new_file_path=target_path,
            old_size=movie.original_file_size,
            new_size=new_size,
            savings_bytes=savings_bytes,
            savings_pct=round((savings_bytes / max(movie.original_file_size or 1, 1)) * 100, 2),
        )
        db.add(log)
        await db.commit()

        await emit_event("replace:completed", {
            "movie_id": movie.id,
            "title": movie.title,
            "old_size": movie.original_file_size,
            "new_size": new_size,
            "savings_bytes": savings_bytes,
        })

        # Refresh Plex
        if config.plex.url and config.plex.token:
            try:
                plex = PlexClient()
                plex.refresh_library()
            except Exception as e:
                logger.warning(f"Plex refresh failed: {e}")

        # Notify Radarr to rescan (so it picks up the new file size/codec)
        if config.radarr.enabled and config.radarr.url and config.radarr.api_key and movie.imdb_id:
            try:
                from backend.integrations.radarr import RadarrClient
                radarr = RadarrClient()
                found = await radarr.rescan_by_imdb(movie.imdb_id)
                if found:
                    logger.info(f"Radarr rescan triggered for {movie.title}")
                else:
                    logger.debug(f"Movie not found in Radarr: {movie.title}")
            except Exception as e:
                logger.warning(f"Radarr rescan failed: {e}")

        # Clean up SABnzbd directory if it was a folder
        if os.path.isdir(storage_path):
            try:
                shutil.rmtree(storage_path, ignore_errors=True)
            except Exception:
                pass

        return True
