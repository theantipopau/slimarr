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


def _cleanup_download_folder(storage_path: str) -> None:
    """Remove the SABnzbd download folder. Called on both success and failure."""
    if not storage_path:
        return
    try:
        if os.path.isdir(storage_path):
            shutil.rmtree(storage_path, ignore_errors=True)
            logger.info(f"Cleaned up download folder: {storage_path!r}")
        elif os.path.isfile(storage_path):
            os.remove(storage_path)
            logger.info(f"Cleaned up download file: {storage_path!r}")
    except Exception as e:
        logger.warning(f"Cleanup of {storage_path!r} failed (non-fatal): {e}")


def _apply_path_mapping(path: str, mappings: list) -> str:
    """
    Translate a Plex-reported file path to the local path Slimarr can write to.
    Mappings: list of dicts with 'plex_path' and 'local_path' keys.
    Example: plex_path=/data/media, local_path=E:/media
    """
    if not path or not mappings:
        return path
    # Normalise separators for comparison
    norm = path.replace("\\", "/")
    for m in mappings:
        plex_pfx = m.get("plex_path", "").rstrip("/\\").replace("\\", "/")
        local_pfx = m.get("local_path", "").rstrip("/\\")
        if plex_pfx and norm.startswith(plex_pfx + "/"):
            remainder = path[len(plex_pfx):].lstrip("/\\")
            mapped = os.path.join(local_pfx, remainder)
            logger.info(f"Path mapping applied: {path!r} → {mapped!r}")
            return mapped
    return path


async def replace_file(download_id: int) -> bool:
    """
    Move the downloaded file to the library, remove the old file,
    refresh Plex. Returns True on success.
    Always cleans up the SABnzbd download folder regardless of outcome.
    """
    from backend.config import get_config
    from backend.integrations.plex import PlexClient

    config = get_config()
    storage_path: str = ""
    if config.automation.dry_run:
        logger.info(f"Dry-run: replacement skipped for download {download_id}")
        return False

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
            err = f"Downloaded storage path missing or inaccessible: {storage_path!r}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            _cleanup_download_folder(storage_path)
            return False

        logger.info(f"Replace starting — storage_path={storage_path!r}")

        # Find the actual video file inside the SABnzbd completed folder
        video_file = _find_video_file(storage_path) if os.path.isdir(storage_path) else storage_path
        if not video_file:
            err = f"No video file found in {storage_path!r}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            _cleanup_download_folder(storage_path)
            return False

        logger.info(f"Video file found: {video_file!r}")

        original_path = movie.file_path
        if not original_path:
            err = "Original file path unknown — cannot replace"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            _cleanup_download_folder(storage_path)
            return False

        logger.info(f"Original Plex path: {original_path!r}")

        # Apply path mappings (Plex-reported path → locally accessible path)
        path_mappings = getattr(config.files, 'plex_path_mappings', [])
        mapped_path = _apply_path_mapping(original_path, path_mappings)
        if mapped_path != original_path:
            logger.info(f"Mapped original path: {mapped_path!r}")

        if not os.path.exists(mapped_path):
            logger.warning(
                f"Original file does not exist at {mapped_path!r} — "
                "it may have been moved or deleted already. Proceeding with placement only."
            )

        # Target path calculation
        target_dir = os.path.dirname(mapped_path)
        ext = os.path.splitext(video_file)[1]
        target_path = os.path.splitext(mapped_path)[0] + ext
        video_size = os.path.getsize(video_file)

        logger.info(f"Target dir: {target_dir!r} — target path: {target_path!r}")

        # Recycle bin step: move original to recycle directory (if configured)
        recycle_dir = config.files.recycling_bin
        recycled_successfully = False
        fallback_backup_path: str | None = None
        if recycle_dir:
            os.makedirs(recycle_dir, exist_ok=True)
            folder_name = os.path.basename(os.path.dirname(mapped_path))
            base_name = os.path.basename(mapped_path)
            recycled_name = f"{folder_name}_{base_name}" if folder_name else base_name
            recycled_path = os.path.join(recycle_dir, recycled_name)
            original_size = os.path.getsize(mapped_path) if os.path.exists(mapped_path) else 0
            recycle_free = shutil.disk_usage(recycle_dir).free
            if original_size > 0 and recycle_free < original_size:
                logger.warning(
                    "Recycle bin has insufficient free space "
                    f"({recycle_free:,} free, {original_size:,} needed); using local backup fallback"
                )
            else:
                try:
                    shutil.move(mapped_path, recycled_path)
                    logger.info(f"Moved original to recycle bin: {recycled_path}")
                    recycled_successfully = True
                except Exception as e:
                    logger.warning(f"Recycle move failed (continuing): {e}")

        if not recycled_successfully and os.path.exists(target_path):
            backup_base = f"{target_path}.slimarr-old"
            fallback_backup_path = backup_base
            suffix = 1
            while os.path.exists(fallback_backup_path):
                fallback_backup_path = f"{backup_base}.{suffix}"
                suffix += 1
            try:
                shutil.move(target_path, fallback_backup_path)
                logger.info(f"Moved existing target aside before replacement: {fallback_backup_path}")
            except Exception as e:
                err = f"Could not move existing target before replacement: {e}"
                logger.error(err)
                dl.status = "failed"
                dl.error_message = err
                await db.commit()
                _cleanup_download_folder(storage_path)
                return False

        # Move new file into place
        if not os.path.isdir(target_dir):
            logger.error(
                f"Target directory does not exist: {target_dir!r} — "
                "check that the Plex library path is accessible from Slimarr, "
                "or configure a path mapping in Settings."
            )
            dl.status = "failed"
            dl.error_message = f"Target directory not found: {target_dir}"
            await db.commit()
            _cleanup_download_folder(storage_path)
            return False

        os.makedirs(target_dir, exist_ok=True)
        target_free = shutil.disk_usage(target_dir).free
        if target_free < video_size and not fallback_backup_path and not os.path.exists(target_path):
            err = (
                "Target drive has insufficient free space for replacement "
                f"({target_free:,} free, {video_size:,} needed)"
            )
            logger.error(err)
            if fallback_backup_path and os.path.exists(fallback_backup_path) and not os.path.exists(target_path):
                try:
                    shutil.move(fallback_backup_path, target_path)
                    logger.info(f"Restored original file after free-space failure: {target_path}")
                except Exception as restore_error:
                    logger.error(f"Failed to restore original file after free-space failure: {restore_error}")
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            _cleanup_download_folder(storage_path)
            return False
        logger.info(f"Moving {video_file!r} → {target_path!r}")
        try:
            shutil.move(video_file, target_path)
        except Exception as e:
            err = f"File move failed: {e}"
            logger.error(err)
            if fallback_backup_path and os.path.exists(fallback_backup_path) and not os.path.exists(target_path):
                try:
                    shutil.move(fallback_backup_path, target_path)
                    logger.info(f"Restored original file after failed replacement: {target_path}")
                except Exception as restore_error:
                    logger.error(f"Failed to restore original file after move failure: {restore_error}")
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            _cleanup_download_folder(storage_path)
            return False

        logger.info(f"File move succeeded. New size: {os.path.getsize(target_path):,} bytes")

        if fallback_backup_path and os.path.exists(fallback_backup_path):
            try:
                os.remove(fallback_backup_path)
                logger.info(f"Deleted fallback backup after successful replacement: {fallback_backup_path}")
            except Exception as e:
                logger.warning(f"Failed to delete fallback backup: {e}")

        # If not recycled and extensions differ, explicitly delete the old file
        if not recycled_successfully and mapped_path != target_path and os.path.exists(mapped_path):
            try:
                os.remove(mapped_path)
                logger.info(f"Deleted old file: {mapped_path}")
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

        # Notify Radarr (rescan / rescan+unmonitor / nothing) based on post_replace_action
        if config.radarr.enabled and config.radarr.url and config.radarr.api_key and movie.imdb_id:
            action = config.radarr.post_replace_action or "rescan"
            if action != "none":
                try:
                    from backend.integrations.radarr import RadarrClient
                    radarr = RadarrClient()
                    found = await radarr.post_replace_action(movie.imdb_id, action)
                    if found:
                        if action == "rescan_unmonitor":
                            logger.info(f"Radarr rescan + unmonitor triggered for {movie.title}")
                        else:
                            logger.info(f"Radarr rescan triggered for {movie.title}")
                    else:
                        logger.debug(f"Movie not found in Radarr: {movie.title}")
                except Exception as e:
                    logger.warning(f"Radarr post-replace action failed: {e}")

        # Clean up the SABnzbd download folder now that we're done with it
        _cleanup_download_folder(storage_path)

        return True
