"""Orphan scanner - find downloads in downloader but not in Slimarr DB."""
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from backend.database import async_session, Download, OrphanedDownload
from backend.config import get_config
from backend.core.search_diagnostics import redact_text
from backend.core.storage import remove_path
from backend.integrations.download_client import encode_job_id, get_download_client
from loguru import logger


async def scan_orphaned_downloads() -> int:
    """
    Scan downloader job history and find orphaned downloads.
    Returns count of newly-found orphans.
    """
    config = get_config()
    downloader = config.download_client  # 'sabnzbd' | 'nzbget'
    new_orphans = 0
    
    try:
        if downloader == "sabnzbd":
            new_orphans = await _scan_sabnzbd_orphans()
        elif downloader == "nzbget":
            new_orphans = await _scan_nzbget_orphans()
        else:
            logger.warning(f"Unknown downloader: {downloader}")
    except Exception as e:
        logger.error("Error scanning orphans: {}", redact_text(str(e)))
    
    return new_orphans


async def _scan_sabnzbd_orphans() -> int:
    """Scan SABnzbd history for orphaned jobs."""
    from backend.integrations.sabnzbd import SABnzbdClient
    
    client = SABnzbdClient()
    new_orphans = 0
    
    try:
        # Get job history from SABnzbd (limit 5000 recent jobs)
        history = await client.get_history(limit=5000)
        now = datetime.now(timezone.utc)

        # Candidate job ids up front, then check both membership sets in one
        # query each instead of two SELECTs per history item (up to 5000).
        candidate_job_ids = [job.get('nzo_id') or job.get('id') for job in history]
        candidate_job_ids = [j for j in candidate_job_ids if j]
        encoded_ids = [encode_job_id("sabnzbd", j) for j in candidate_job_ids]

        async with async_session() as session:
            tracked_nzo_ids: set[str] = set()
            recorded_orphan_ids: set[str] = set()
            if candidate_job_ids:
                tracked_result = await session.execute(
                    select(Download.nzo_id).where(
                        Download.nzo_id.in_(candidate_job_ids + encoded_ids)
                    )
                )
                tracked_nzo_ids = {row[0] for row in tracked_result.all()}

                orphan_result = await session.execute(
                    select(OrphanedDownload.downloader_job_id).where(
                        OrphanedDownload.downloader_job_id.in_(candidate_job_ids)
                    )
                )
                recorded_orphan_ids = {row[0] for row in orphan_result.all()}

            for job in history:
                try:
                    job_id = job.get('nzo_id') or job.get('id')
                    if not job_id:
                        continue

                    # Already tracked. New rows store client-prefixed IDs
                    # (sabnzbd:<id>), while older rows may contain the raw ID.
                    if job_id in tracked_nzo_ids or encode_job_id("sabnzbd", job_id) in tracked_nzo_ids:
                        continue  # Already tracked

                    # This is an orphan - calculate age
                    completed_time = job.get('completed', 0)
                    if completed_time:
                        completed_dt = datetime.fromtimestamp(completed_time, tz=timezone.utc)
                        age_hours = int((now - completed_dt).total_seconds() / 3600)
                    else:
                        age_hours = None

                    # Only flag orphans older than 24 hours
                    if age_hours and age_hours < 24:
                        continue

                    if job_id in recorded_orphan_ids:
                        continue  # Already recorded

                    # Add to orphaned_downloads
                    orphan = OrphanedDownload(
                        downloader_name="sabnzbd",
                        downloader_job_id=job_id,
                        release_name=job.get('name'),
                        storage_path=job.get('storage'),
                        found_at=now,
                        age_hours=age_hours,
                    )
                    session.add(orphan)
                    recorded_orphan_ids.add(job_id)
                    new_orphans += 1

                    logger.info(
                        "Found orphaned download: {} ({}h old)",
                        redact_text(str(job.get("name") or "")),
                        age_hours,
                    )
                except Exception as item_error:
                    # One malformed history entry shouldn't discard every
                    # orphan already queued for commit in this same scan.
                    logger.warning(
                        "Skipping malformed SABnzbd history entry: {}",
                        redact_text(str(item_error)),
                    )

            await session.commit()

    except Exception as e:
        logger.error("Error scanning SABnzbd orphans: {}", redact_text(str(e)))

    return new_orphans


async def _scan_nzbget_orphans() -> int:
    """Scan NZBGet history for orphaned jobs."""
    from backend.integrations.nzbget import NZBGetClient
    
    client = NZBGetClient()
    new_orphans = 0
    
    try:
        # Get full history from NZBGet
        history = await client.history(False)
        now = datetime.now(timezone.utc)

        candidate_job_ids = [str(job.get('NZBID', '')) for job in history]
        candidate_job_ids = [j for j in candidate_job_ids if j]
        encoded_ids = [encode_job_id("nzbget", j) for j in candidate_job_ids]

        async with async_session() as session:
            tracked_nzo_ids: set[str] = set()
            recorded_orphan_ids: set[str] = set()
            if candidate_job_ids:
                tracked_result = await session.execute(
                    select(Download.nzo_id).where(
                        Download.nzo_id.in_(candidate_job_ids + encoded_ids)
                    )
                )
                tracked_nzo_ids = {row[0] for row in tracked_result.all()}

                orphan_result = await session.execute(
                    select(OrphanedDownload.downloader_job_id).where(
                        OrphanedDownload.downloader_job_id.in_(candidate_job_ids)
                    )
                )
                recorded_orphan_ids = {row[0] for row in orphan_result.all()}

            for job in history:
                try:
                    job_id = str(job.get('NZBID', ''))
                    if not job_id:
                        continue

                    # Already tracked. New rows store client-prefixed IDs
                    # (nzbget:<id>), while older rows may contain the raw ID.
                    if job_id in tracked_nzo_ids or encode_job_id("nzbget", job_id) in tracked_nzo_ids:
                        continue

                    # Calculate age
                    completed_time = job.get('HistoryTime', 0)
                    if completed_time:
                        completed_dt = datetime.fromtimestamp(completed_time, tz=timezone.utc)
                        age_hours = int((now - completed_dt).total_seconds() / 3600)
                    else:
                        age_hours = None

                    # Only flag old orphans
                    if age_hours and age_hours < 24:
                        continue

                    if job_id in recorded_orphan_ids:
                        continue

                    # Add orphan
                    orphan = OrphanedDownload(
                        downloader_name="nzbget",
                        downloader_job_id=job_id,
                        release_name=job.get('Name'),
                        storage_path=job.get('DestDir'),
                        found_at=now,
                        age_hours=age_hours,
                    )
                    session.add(orphan)
                    recorded_orphan_ids.add(job_id)
                    new_orphans += 1

                    logger.info(
                        "Found orphaned NZBGet job: {} ({}h old)",
                        redact_text(str(job.get("Name") or "")),
                        age_hours,
                    )
                except Exception as item_error:
                    # One malformed history entry shouldn't discard every
                    # orphan already queued for commit in this same scan.
                    logger.warning(
                        "Skipping malformed NZBGet history entry: {}",
                        redact_text(str(item_error)),
                    )

            await session.commit()

    except Exception as e:
        logger.error("Error scanning NZBGet orphans: {}", redact_text(str(e)))

    return new_orphans


async def cleanup_orphaned_download(orphan_id: int) -> tuple[bool, Optional[str]]:
    """
    Manually clean up an orphaned download.
    Returns (success, message).
    """
    async with async_session() as session:
        result = await session.execute(
            select(OrphanedDownload).where(OrphanedDownload.id == orphan_id)
        )
        orphan = result.scalars().first()
        
        if not orphan:
            return False, "Orphan not found"

        downloader_name = orphan.downloader_name
        job_id = orphan.downloader_job_id
        storage_path = orphan.storage_path
        release_name = orphan.release_name

        downloader_purged = False
        folder_deleted = False

        if job_id:
            try:
                client = get_download_client(downloader_name)
                downloader_purged = await client.purge_job(job_id)
            except Exception as e:
                logger.warning(
                    "Failed to purge orphan job {} from {}: {}",
                    job_id,
                    downloader_name,
                    redact_text(str(e)),
                )

        if storage_path:
            try:
                result = await remove_path(
                    storage_path,
                    get_config(),
                    purpose="orphan_download_cleanup",
                    recursive=True,
                )
                folder_deleted = result.status in {"completed", "skipped"}
            except Exception as e:
                logger.warning(
                    "Failed to delete orphan path '{}': {}",
                    storage_path,
                    redact_text(str(e)),
                )

        if downloader_purged or folder_deleted or not storage_path:
            await session.delete(orphan)
            await session.commit()
            logger.info(
                f"Cleaned orphaned download: {release_name} "
                f"(folder_deleted={folder_deleted}, downloader_purged={downloader_purged})"
            )
            return True, "Orphan cleaned up"

        orphan.cleanup_scheduled = True
        orphan.cleanup_at = datetime.now(timezone.utc)
        await session.commit()
        return False, "Cleanup attempted, but no downloader job or folder could be removed"


async def auto_cleanup_old_orphans(days_old: int = 7) -> int:
    """
    Auto-delete orphaned downloads older than specified days.

    Only removes the tracking row once the on-disk folder is actually gone
    (or there was never a storage path to remove) — mirroring
    cleanup_orphaned_download()'s success-gated deletion. A failed removal
    (permission error, transient lock, already-gone parent dir) instead marks
    the row cleanup_scheduled so it stops cluttering the active orphan list
    but is retried on the next daily run, rather than deleting Slimarr's only
    record that the file might still be sitting on disk.

    Returns count of tracking rows actually deleted.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    deleted_count = 0

    async with async_session() as session:
        # Find old orphans
        result = await session.execute(
            select(OrphanedDownload).where(
                OrphanedDownload.found_at < cutoff
            )
        )
        orphans = result.scalars().all()

        for orphan in orphans:
            folder_deleted = True
            if orphan.storage_path:
                folder_deleted = False
                try:
                    result = await remove_path(
                        orphan.storage_path,
                        get_config(),
                        purpose="old_orphan_auto_cleanup",
                        recursive=True,
                    )
                    folder_deleted = result.status in {"completed", "skipped"}
                except Exception as e:
                    logger.warning(
                        "Failed to delete orphan path '{}': {}",
                        orphan.storage_path,
                        redact_text(str(e)),
                    )

            if folder_deleted:
                await session.delete(orphan)
                deleted_count += 1
            else:
                orphan.cleanup_scheduled = True
                orphan.cleanup_at = datetime.now(timezone.utc)

        await session.commit()

    if deleted_count > 0:
        logger.info(f"Auto-cleaned {deleted_count} old orphaned downloads (>{days_old} days)")

    return deleted_count


async def get_orphaned_downloads(limit: int = 100) -> list[dict]:
    """Get active orphaned downloads."""
    async with async_session() as session:
        result = await session.execute(
            select(OrphanedDownload)
            .where(OrphanedDownload.cleanup_scheduled == False)
            .order_by(OrphanedDownload.found_at.desc())
            .limit(limit)
        )
        orphans = result.scalars().all()
    
    return [
        {
            "id": o.id,
            "downloader_name": o.downloader_name,
            "downloader_job_id": o.downloader_job_id,
            "release_name": o.release_name,
            "storage_path": o.storage_path,
            "found_at": o.found_at.isoformat() if o.found_at else None,
            "age_hours": o.age_hours,
        }
        for o in orphans
    ]
