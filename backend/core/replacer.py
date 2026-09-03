"""
File replacer - moves the downloaded file into place and refreshes Plex.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import json
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from backend.core.media_probe import probe_media_file
from backend.core.parser import normalize_codec, normalize_resolution, parse_release_title
from backend.core.storage import move_path, path_matches_prefix, preflight_storage_path, remove_path
from backend.database import ActivityLog, Download, Movie, ReplacementRecoveryRecord, async_session
from backend.realtime.events import emit_event

SUPPORTED_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v"}


def _find_video_file(directory: str) -> str | None:
    for root, _dirs, files in os.walk(directory):
        for f in files:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                return os.path.join(root, f)
    return None


# All of these can resolve to a NAS/network path (recycling bin, Plex library
# mount, SABnzbd staging dir). Running them straight on the event loop blocks
# the entire app — including unrelated API requests and the scheduler — for as
# long as the share takes to respond, which on a slow/sleeping NAS can be
# seconds. Every call goes through a worker thread instead.
async def _exists(path: str) -> bool:
    return await asyncio.to_thread(os.path.exists, path)


async def _isdir(path: str) -> bool:
    return await asyncio.to_thread(os.path.isdir, path)


async def _getsize(path: str) -> int:
    return await asyncio.to_thread(os.path.getsize, path)


async def _makedirs(path: str) -> None:
    await asyncio.to_thread(os.makedirs, path, exist_ok=True)


async def _disk_free(path: str) -> int:
    return await asyncio.to_thread(lambda: shutil.disk_usage(path).free)


async def _find_video_file_async(directory: str) -> str | None:
    return await asyncio.to_thread(_find_video_file, directory)


async def _remove_with_retry(
    path: str,
    config,
    *,
    purpose: str,
    attempts: int = 4,
    delay_seconds: float = 5.0,
) -> None:
    """remove_path(), retrying a few times on a transient file-lock error —
    the delete-side counterpart to _move_with_retry below. Without this, a
    brief lock (Plex/AV touching the file right after replacement) leaves a
    stale copy behind permanently, since these cleanup steps run once,
    after the movie/download rows have already moved on to their final
    state, with nothing to retry them on the next cycle."""
    for attempt in range(1, attempts + 1):
        try:
            return await remove_path(path, config, purpose=purpose)
        except Exception as exc:
            if attempt >= attempts or not _is_transient_lock_error(exc):
                raise
            logger.warning(
                "{} attempt {}/{} hit a transient file lock on {!r}; retrying in {:.0f}s: {}",
                purpose,
                attempt,
                attempts,
                path,
                delay_seconds,
                exc,
            )
            await asyncio.sleep(delay_seconds)


def _is_transient_lock_error(exc: BaseException) -> bool:
    """True for OS-level "file in use" errors (Windows WinError 32/33, or the
    POSIX equivalents) that are usually cleared within a few seconds — e.g. a
    brief AV scan or Plex/thumbnail-generator handle on the file we're about
    to move aside. Distinguishing these from permanent errors (permissions,
    missing path) lets the caller retry a couple of times instead of failing
    the whole replacement outright and re-downloading the same release again
    on the next cycle only to hit the exact same transient lock.
    """
    winerror = getattr(exc, "winerror", None)
    if winerror in (32, 33):
        return True
    return isinstance(exc, PermissionError)


async def _move_with_retry(
    source: str,
    target: str,
    config,
    *,
    purpose: str,
    required_bytes: int | None = None,
    attempts: int = 4,
    delay_seconds: float = 5.0,
):
    """move_path(), retrying a few times on a transient file-lock error."""
    for attempt in range(1, attempts + 1):
        try:
            return await move_path(source, target, config, purpose=purpose, required_bytes=required_bytes)
        except Exception as exc:
            if attempt >= attempts or not _is_transient_lock_error(exc):
                raise
            logger.warning(
                "{} attempt {}/{} hit a transient file lock on {!r}; retrying in {:.0f}s: {}",
                purpose,
                attempt,
                attempts,
                target,
                delay_seconds,
                exc,
            )
            await asyncio.sleep(delay_seconds)


async def _verify_downloaded_file(video_file: str, config) -> str | None:
    """Sanity-check a downloaded file before it replaces a working library copy.

    Returns an error description if verification fails, or None if the file
    looks usable. Always checks for a non-empty file (cheap, no false
    positives). Only probes the actual media streams when
    `files.enable_media_probe` is also on, and a probe failure is logged as a
    warning rather than blocking replacement, since pymediainfo can be flaky
    on some containers and we don't want to invent a new failure mode for a
    "verify" feature that was previously a no-op.
    """
    size = await _getsize(video_file)
    if size <= 0:
        return f"downloaded file is empty: {video_file!r}"

    if getattr(config.files, "enable_media_probe", False):
        probe = await asyncio.to_thread(probe_media_file, video_file)
        if not probe or not (probe.get("video_codec") or probe.get("resolution")):
            logger.warning(
                "Downloaded file verification probe found no usable video stream "
                "(continuing anyway): {!r}",
                video_file,
            )

    return None


async def _cleanup_download_folder(storage_path: str, config) -> None:
    """Remove the SABnzbd download folder. Called on both success and failure."""
    if not storage_path:
        return
    try:
        result = await remove_path(
            storage_path,
            config,
            purpose="replacement_download_staging_cleanup",
            recursive=True,
        )
        logger.info(f"Cleaned up download staging path: {storage_path!r} ({result.status})")
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
            logger.info(f"Path mapping applied: {path!r} -> {mapped!r}")
            return mapped
    return path


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _create_replacement_recovery_record(
    db,
    *,
    download_id: int,
    movie: Movie,
    original_path: str,
    mapped_path: str,
    target_path: str,
    video_file_path: str,
    storage_path: str,
) -> ReplacementRecoveryRecord:
    record = ReplacementRecoveryRecord(
        download_id=download_id,
        movie_id=movie.id,
        movie_title=movie.title,
        status="running",
        phase="preflight_complete",
        original_path=original_path,
        mapped_path=mapped_path,
        target_path=target_path,
        video_file_path=video_file_path,
        storage_path=storage_path,
        details=json.dumps({"quality_intent": getattr(movie, "quality_intent", None)}),
        updated_at=_utc_now_naive(),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def _mark_replacement_recovery(
    db,
    record: ReplacementRecoveryRecord | None,
    *,
    phase: str,
    status: str = "running",
    error: str | None = None,
    recycle_path: str | None = None,
    fallback_backup_path: str | None = None,
) -> None:
    if record is None:
        return
    record.phase = phase
    record.status = status
    record.updated_at = _utc_now_naive()
    if error is not None:
        record.error_message = error
    if recycle_path is not None:
        record.recycle_path = recycle_path
    if fallback_backup_path is not None:
        record.fallback_backup_path = fallback_backup_path
    if status in {"completed", "failed", "recovery_required"}:
        record.completed_at = _utc_now_naive()
    await db.commit()


async def _run_radarr_post_replace(movie: Movie, config) -> None:
    """Dispatch Radarr post-replace action based on configuration."""
    if not (config.radarr.enabled and config.radarr.url and config.radarr.api_key and movie.imdb_id):
        return

    action = config.radarr.post_replace_action or "rescan"
    if action == "none":
        return

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
    recovery_record: ReplacementRecoveryRecord | None = None
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
        if not storage_path or not await _exists(storage_path):
            err = f"Downloaded storage path missing or inaccessible: {storage_path!r}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False

        logger.info(f"Replace starting - storage_path={storage_path!r}")

        # Find the actual video file inside the SABnzbd completed folder
        video_file = (
            await _find_video_file_async(storage_path)
            if await _isdir(storage_path)
            else storage_path
        )
        if not video_file:
            err = f"No video file found in {storage_path!r}"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False

        logger.info(f"Video file found: {video_file!r}")

        # Fallback must match FilesConfig.verify_after_download's actual default
        # (True) so a missing attribute never silently disables this safety check.
        if getattr(config.files, "verify_after_download", True):
            verify_error = await _verify_downloaded_file(video_file, config)
            if verify_error:
                logger.error(f"Download verification failed: {verify_error}")
                dl.status = "failed"
                dl.error_message = f"Download verification failed: {verify_error}"
                await db.commit()
                await _cleanup_download_folder(storage_path, config)
                return False

        original_path = movie.file_path
        if not original_path:
            err = "Original file path unknown - cannot replace"
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False

        logger.info(f"Original Plex path: {original_path!r}")

        # Apply path mappings (Plex-reported path -> locally accessible path)
        path_mappings = getattr(config.files, 'plex_path_mappings', [])
        mapped_path = _apply_path_mapping(original_path, path_mappings)
        if mapped_path != original_path:
            logger.info(f"Mapped original path: {mapped_path!r}")

        if not await _exists(mapped_path):
            logger.warning(
                f"Original file does not exist at {mapped_path!r} - "
                "it may have been moved or deleted already. Proceeding with placement only."
            )

        # Target path calculation
        target_dir = os.path.dirname(mapped_path)
        ext = os.path.splitext(video_file)[1]
        target_path = os.path.splitext(mapped_path)[0] + ext
        video_size = await _getsize(video_file)

        logger.info(f"Target dir: {target_dir!r} - target path: {target_path!r}")

        target_preflight = await asyncio.to_thread(
            preflight_storage_path,
            target_path,
            config,
            required_bytes=0 if await _exists(target_path) else video_size,
            purpose="place_replacement",
        )
        for message in target_preflight.messages:
            logger.info(f"Replacement target preflight: {message}")
        if target_preflight.status == "block":
            err = "Replacement target preflight blocked operation: " + "; ".join(target_preflight.messages)
            logger.error(err)
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False

        recovery_record = await _create_replacement_recovery_record(
            db,
            download_id=download_id,
            movie=movie,
            original_path=original_path,
            mapped_path=mapped_path,
            target_path=target_path,
            video_file_path=video_file,
            storage_path=storage_path,
        )

        # Recycle bin step: move original to recycle directory (if configured)
        recycle_dir = config.files.recycling_bin
        recycled_successfully = False
        fallback_backup_path: str | None = None
        if recycle_dir:
            await _makedirs(recycle_dir)
            folder_name = os.path.basename(os.path.dirname(mapped_path))
            base_name = os.path.basename(mapped_path)
            recycled_name = f"{folder_name}_{base_name}" if folder_name else base_name
            recycled_path = os.path.join(recycle_dir, recycled_name)
            original_size = await _getsize(mapped_path) if await _exists(mapped_path) else 0
            recycle_preflight = await asyncio.to_thread(
                preflight_storage_path,
                recycled_path,
                config,
                required_bytes=original_size,
                purpose="recycle_original",
            )
            if recycle_preflight.status == "block":
                logger.warning(
                    "Recycle bin preflight blocked move; using local backup fallback: {}",
                    "; ".join(recycle_preflight.messages),
                )
            else:
                try:
                    await _mark_replacement_recovery(
                        db,
                        recovery_record,
                        phase="recycle_original_started",
                        recycle_path=recycled_path,
                    )
                    result = await _move_with_retry(
                        mapped_path,
                        recycled_path,
                        config,
                        purpose="recycle_original",
                    )
                    logger.info(f"Moved original to recycle bin: {recycled_path} ({result.status})")
                    recycled_successfully = True
                    await _mark_replacement_recovery(
                        db,
                        recovery_record,
                        phase="recycle_original_completed",
                        recycle_path=recycled_path,
                    )
                except Exception as e:
                    logger.warning(f"Recycle move failed (continuing): {e}")
                    await _mark_replacement_recovery(
                        db,
                        recovery_record,
                        phase="recycle_original_failed",
                        error=str(e),
                        recycle_path=recycled_path,
                    )

        if not recycled_successfully and await _exists(target_path):
            backup_base = f"{target_path}.slimarr-old"
            fallback_backup_path = backup_base
            suffix = 1
            while await _exists(fallback_backup_path):
                fallback_backup_path = f"{backup_base}.{suffix}"
                suffix += 1
            try:
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="backup_existing_target_started",
                    fallback_backup_path=fallback_backup_path,
                )
                await _move_with_retry(
                    target_path,
                    fallback_backup_path,
                    config,
                    purpose="backup_existing_target",
                    required_bytes=0,
                )
                logger.info(f"Moved existing target aside before replacement: {fallback_backup_path}")
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="backup_existing_target_completed",
                    fallback_backup_path=fallback_backup_path,
                )
            except Exception as e:
                err = f"Could not move existing target before replacement: {e}"
                logger.error(err)
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="backup_existing_target_failed",
                    status="failed",
                    error=err,
                    fallback_backup_path=fallback_backup_path,
                )
                dl.status = "failed"
                dl.error_message = err
                await db.commit()
                await _cleanup_download_folder(storage_path, config)
                return False

        # Move new file into place
        if not await _isdir(target_dir):
            logger.error(
                f"Target directory does not exist: {target_dir!r} - "
                "check that the Plex library path is accessible from Slimarr, "
                "or configure a path mapping in Settings."
            )
            await _mark_replacement_recovery(
                db,
                recovery_record,
                phase="target_directory_missing",
                status="recovery_required" if recycled_successfully or fallback_backup_path else "failed",
                error=f"Target directory not found: {target_dir}",
                fallback_backup_path=fallback_backup_path,
            )
            dl.status = "failed"
            dl.error_message = f"Target directory not found: {target_dir}"
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False

        await _makedirs(target_dir)
        target_free = await _disk_free(target_dir)
        if target_free < video_size and not fallback_backup_path and not await _exists(target_path):
            err = (
                "Target drive has insufficient free space for replacement "
                f"({target_free:,} free, {video_size:,} needed)"
            )
            logger.error(err)
            if (
                fallback_backup_path
                and await _exists(fallback_backup_path)
                and not await _exists(target_path)
            ):
                try:
                    await move_path(
                        fallback_backup_path,
                        target_path,
                        config,
                        purpose="restore_original_after_free_space_failure",
                        required_bytes=0,
                    )
                    logger.info(f"Restored original file after free-space failure: {target_path}")
                except Exception as restore_error:
                    logger.error(f"Failed to restore original file after free-space failure: {restore_error}")
            await _mark_replacement_recovery(
                db,
                recovery_record,
                phase="free_space_preflight_failed",
                status="recovery_required" if recycled_successfully else "failed",
                error=err,
                fallback_backup_path=fallback_backup_path,
            )
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False
        logger.info(f"Moving {video_file!r} -> {target_path!r}")
        try:
            await _mark_replacement_recovery(
                db,
                recovery_record,
                phase="place_replacement_started",
                fallback_backup_path=fallback_backup_path,
            )
            await move_path(video_file, target_path, config, purpose="place_replacement")
            await _mark_replacement_recovery(
                db,
                recovery_record,
                phase="place_replacement_completed",
                fallback_backup_path=fallback_backup_path,
            )
        except Exception as e:
            err = f"File move failed: {e}"
            logger.error(err)
            restored_after_failure = False
            if (
                fallback_backup_path
                and await _exists(fallback_backup_path)
                and not await _exists(target_path)
            ):
                try:
                    await move_path(
                        fallback_backup_path,
                        target_path,
                        config,
                        purpose="restore_original_after_move_failure",
                        required_bytes=0,
                    )
                    logger.info(f"Restored original file after failed replacement: {target_path}")
                    restored_after_failure = True
                except Exception as restore_error:
                    logger.error(f"Failed to restore original file after move failure: {restore_error}")
                    await _mark_replacement_recovery(
                        db,
                        recovery_record,
                        phase="restore_original_after_move_failure_failed",
                        status="recovery_required",
                        error=f"{err}; restore failed: {restore_error}",
                        fallback_backup_path=fallback_backup_path,
                    )
            if restored_after_failure:
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="restore_original_after_move_failure_completed",
                    status="failed",
                    error=err,
                    fallback_backup_path=fallback_backup_path,
                )
            elif recycled_successfully:
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="place_replacement_failed_original_recycled",
                    status="recovery_required",
                    error=err,
                    fallback_backup_path=fallback_backup_path,
                )
            else:
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="place_replacement_failed",
                    status="failed",
                    error=err,
                    fallback_backup_path=fallback_backup_path,
                )
            dl.status = "failed"
            dl.error_message = err
            await db.commit()
            await _cleanup_download_folder(storage_path, config)
            return False

        logger.info(f"File move succeeded. New size: {await _getsize(target_path):,} bytes")

        # Re-probe the file now sitting at target_path so the movie record reflects
        # what was actually placed, not the stats of the file it replaced. Without
        # this, resolution/codec/bitrate stay stuck at the previous file's values
        # forever (the scanner prefers Plex's own reported media info, which often
        # doesn't get re-analyzed by a plain library refresh for a path Plex
        # already knows), which makes the replaced copy look perpetually like a
        # low-quality/mismatched file and keeps triggering further replacements.
        #
        # This runs unconditionally (not gated on files.enable_media_probe, which
        # only controls the scanner's library-wide probing) because it's a single
        # probe of the one file we just finished writing, not a bulk library scan.
        # It still respects the NAS-path skip so we don't add extra SMB/NFS reads
        # for a target library path that lives on a slow/sleeping NAS.
        new_probe: dict = {}
        nas_prefixes = list(getattr(config.files, "nas_path_prefixes", None) or [])
        nas_probe_allowed = bool(getattr(config.files, "nas_probe_enabled", False))
        target_norm = target_path.replace("\\", "/")
        is_target_nas = target_norm.startswith("//") or path_matches_prefix(target_path, nas_prefixes)
        if not is_target_nas or nas_probe_allowed:
            new_probe = await asyncio.to_thread(probe_media_file, target_path)
        else:
            logger.debug("Skipping post-replacement media probe for network path: {}", target_path)

        if fallback_backup_path and await _exists(fallback_backup_path):
            try:
                await _remove_with_retry(
                    fallback_backup_path,
                    config,
                    purpose="delete_fallback_backup_after_success",
                )
                logger.info(f"Deleted fallback backup after successful replacement: {fallback_backup_path}")
            except Exception as e:
                logger.warning(f"Failed to delete fallback backup: {e}")
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="delete_fallback_backup_failed",
                    error=str(e),
                    fallback_backup_path=fallback_backup_path,
                )

        # If not recycled and extensions differ, explicitly delete the old file
        if not recycled_successfully and mapped_path != target_path and await _exists(mapped_path):
            try:
                await _remove_with_retry(mapped_path, config, purpose="delete_old_extension_after_replacement")
                logger.info(f"Deleted old file: {mapped_path}")
            except Exception as e:
                logger.warning(f"Failed to delete old file: {e}")
                await _mark_replacement_recovery(
                    db,
                    recovery_record,
                    phase="delete_old_extension_failed",
                    error=str(e),
                )

        # Update movie record
        new_size = await _getsize(target_path)
        if movie.original_file_size is None:
            movie.original_file_size = movie.file_size
        movie.file_path = target_path
        movie.file_size = new_size
        movie.status = "improved"
        if new_probe.get("resolution"):
            movie.resolution = normalize_resolution(new_probe["resolution"])
        if new_probe.get("video_codec"):
            movie.video_codec = normalize_codec(new_probe["video_codec"])
        if new_probe.get("audio_codec"):
            movie.audio_codec = new_probe["audio_codec"]
        if new_probe.get("bitrate_kbps"):
            movie.bitrate = new_probe["bitrate_kbps"]
        # The release title is the most reliable source-type signal available —
        # far more so than re-guessing from a Plex-renamed filename on the next
        # scan — so capture it here while we know exactly which release this is.
        if dl.release_title:
            replaced_parsed = parse_release_title(dl.release_title)
            if replaced_parsed.source:
                movie.source_type = replaced_parsed.source

        # Update download record
        dl.status = "replaced"
        dl.completed_at = datetime.now(timezone.utc)

        # Log activity
        savings_bytes = (movie.original_file_size or 0) - new_size
        # Keep cumulative per-movie savings and replacement count up to date.
        if savings_bytes > 0:
            movie.total_savings = int(movie.total_savings or 0) + savings_bytes
        movie.times_replaced = int(movie.times_replaced or 0) + 1
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
        await _mark_replacement_recovery(
            db,
            recovery_record,
            phase="db_committed",
            status="completed",
            fallback_backup_path=fallback_backup_path,
        )

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
        await _run_radarr_post_replace(movie, config)

        # Clean up the SABnzbd download folder now that we're done with it
        await _cleanup_download_folder(storage_path, config)

        return True
