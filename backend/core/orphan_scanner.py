"""Orphan scanner - find downloads in downloader but not in Slimarr DB."""
import os
import shutil
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from backend.database import async_session, Download, OrphanedDownload
from backend.config import get_config
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
        logger.error(f"Error scanning orphans: {e}")
    
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
        
        async with async_session() as session:
            for job in history:
                job_id = job.get('nzo_id') or job.get('id')
                if not job_id:
                    continue
                
                # Check if this job is in our DB. New rows store client-prefixed
                # IDs (sabnzbd:<id>), while older rows may contain the raw ID.
                result = await session.execute(
                    select(Download).where(
                        Download.nzo_id.in_([job_id, encode_job_id("sabnzbd", job_id)])
                    )
                )
                existing = result.scalars().first()
                
                if existing:
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
                
                # Check if already in orphaned_downloads table
                orphan_result = await session.execute(
                    select(OrphanedDownload).where(
                        OrphanedDownload.downloader_job_id == job_id
                    )
                )
                if orphan_result.scalars().first():
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
                new_orphans += 1
                
                logger.info(f"Found orphaned download: {job.get('name')} ({age_hours}h old)")
            
            await session.commit()
    
    except Exception as e:
        logger.error(f"Error scanning SABnzbd orphans: {e}")
    
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
        
        async with async_session() as session:
            for job in history:
                job_id = str(job.get('NZBID', ''))
                if not job_id:
                    continue
                
                # Check if in our DB. New rows store client-prefixed IDs
                # (nzbget:<id>), while older rows may contain the raw ID.
                result = await session.execute(
                    select(Download).where(
                        Download.nzo_id.in_([job_id, encode_job_id("nzbget", job_id)])
                    )
                )
                existing = result.scalars().first()
                
                if existing:
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
                
                # Check if already recorded
                orphan_result = await session.execute(
                    select(OrphanedDownload).where(
                        OrphanedDownload.downloader_job_id == job_id
                    )
                )
                if orphan_result.scalars().first():
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
                new_orphans += 1
                
                logger.info(f"Found orphaned NZBGet job: {job.get('Name')} ({age_hours}h old)")
            
            await session.commit()
    
    except Exception as e:
        logger.error(f"Error scanning NZBGet orphans: {e}")
    
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
                logger.warning(f"Failed to purge orphan job {job_id} from {downloader_name}: {e}")

        if storage_path:
            try:
                if os.path.isdir(storage_path):
                    shutil.rmtree(storage_path, ignore_errors=False)
                    folder_deleted = True
                elif os.path.isfile(storage_path):
                    os.remove(storage_path)
                    folder_deleted = True
            except Exception as e:
                logger.warning(f"Failed to delete orphan path '{storage_path}': {e}")

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
    Returns count deleted.
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
            if orphan.storage_path:
                try:
                    if os.path.isdir(orphan.storage_path):
                        shutil.rmtree(orphan.storage_path, ignore_errors=False)
                    elif os.path.isfile(orphan.storage_path):
                        os.remove(orphan.storage_path)
                except Exception as e:
                    logger.warning(f"Failed to delete orphan path '{orphan.storage_path}': {e}")
            await session.delete(orphan)
            deleted_count += 1
        
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
