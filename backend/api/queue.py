"""Download queue API routes."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select

from backend.auth.dependencies import get_current_user
from backend.database import Download, async_session

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/active")
async def get_active_downloads(user=Depends(get_current_user)):
    async with async_session() as db:
        result = await db.execute(
            select(Download)
            .where(Download.status == "downloading")
            .order_by(Download.started_at.desc())
        )
        downloads = result.scalars().all()
    return [_dl_dict(d) for d in downloads]


@router.get("/recent")
async def get_recent_downloads(limit: int = 20, user=Depends(get_current_user)):
    async with async_session() as db:
        result = await db.execute(
            select(Download)
            .order_by(Download.started_at.desc())
            .limit(limit)
        )
        downloads = result.scalars().all()
    return [_dl_dict(d) for d in downloads]


@router.get("/failed")
async def get_failed_downloads(limit: int = 50, user=Depends(get_current_user)):
    """List all failed downloads with cleanup status."""
    async with async_session() as db:
        result = await db.execute(
            select(Download)
            .where(Download.status == "failed")
            .order_by(Download.completed_at.desc())
            .limit(limit)
        )
        downloads = result.scalars().all()
    return [_dl_dict(d) for d in downloads]


@router.post("/{download_id}/cleanup")
async def cleanup_failed_download_endpoint(download_id: int, user=Depends(get_current_user)):
    """Manually trigger cleanup of a failed download."""
    from backend.core.downloader import cleanup_failed_download

    result = await cleanup_failed_download(download_id)
    return result




@router.post("/{download_id}/retry")
async def retry_failed_download_endpoint(
    download_id: int,
    background: BackgroundTasks,
    user=Depends(get_current_user),
):
    """Retry a failed download with the next best candidate."""
    from backend.core.retry_ladder import retry_failed_download
    from backend.core.downloader import monitor_download
    
    success, message, retried_download_id = await retry_failed_download(download_id)

    if success and retried_download_id:
        background.add_task(monitor_download, retried_download_id)
    
    return {
        "success": success,
        "message": message,
        "download_id": download_id,
        "retried_download_id": retried_download_id,
    }




@router.get("/orphaned")
async def get_orphaned_downloads(limit: int = 100, user=Depends(get_current_user)):
    """Get list of orphaned downloads not in Slimarr DB."""
    from backend.core.orphan_scanner import get_orphaned_downloads
    
    orphans = await get_orphaned_downloads(limit=limit)
    return orphans


@router.post("/orphaned/{orphan_id}/cleanup")
async def cleanup_orphaned_download_endpoint(orphan_id: int, user=Depends(get_current_user)):
    """Mark an orphaned download for cleanup."""
    from backend.core.orphan_scanner import cleanup_orphaned_download
    
    success, message = await cleanup_orphaned_download(orphan_id)
    
    return {
        "success": success,
        "message": message,
        "orphan_id": orphan_id,
    }


def _dl_dict(d: Download) -> dict:
    return {
        "id": d.id,
        "movie_id": d.movie_id,
        "release_title": d.release_title,
        "status": d.status,
        "progress_pct": d.progress_pct,
        "expected_size": d.expected_size,
        "nzo_id": d.nzo_id,
        "storage_path": d.storage_path,
        "cleanup_status": d.cleanup_status,
        "retry_count": d.retry_count,
        "grabbed_at": d.grabbed_at.isoformat() if d.grabbed_at else None,
        "last_error_at": d.last_error_at.isoformat() if d.last_error_at else None,
        "started_at": d.started_at.isoformat() if d.started_at else None,
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        "error_message": d.error_message,
    }
