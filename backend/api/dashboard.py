"""Dashboard API routes."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from backend.auth.dependencies import get_current_user
from backend.database import ActivityLog, Download, Movie, async_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(user=Depends(get_current_user)):
    async with async_session() as db:
        total_movies = (await db.execute(select(func.count()).select_from(Movie))).scalar_one()
        improved = (await db.execute(
            select(func.count()).select_from(Movie).where(Movie.status == "improved")
        )).scalar_one()
        failed = (await db.execute(
            select(func.count()).select_from(Movie).where(Movie.status == "failed")
        )).scalar_one()
        pending_candidates = (await db.execute(
            select(func.count()).select_from(Movie).where(Movie.status.in_(["pending", "review_required"]))
        )).scalar_one()
        library_size = (await db.execute(select(func.sum(Movie.file_size)))).scalar_one() or 0
        last_scan = (await db.execute(select(func.max(Movie.last_scanned)))).scalar_one()

        savings_row = await db.execute(
            select(func.sum(ActivityLog.savings_bytes)).where(
                ActivityLog.event == "replace:completed"
            )
        )
        total_savings = savings_row.scalar_one() or 0

        active_downloads = (await db.execute(
            select(func.count()).select_from(Download).where(
                Download.status.in_(["queued", "submitting", "downloading"])
            )
        )).scalar_one()

    return {
        "total_movies": total_movies,
        "improved": improved,
        "pending": pending_candidates,
        "failed_items": failed,
        "library_size_bytes": library_size,
        "total_savings_bytes": total_savings,
        "active_downloads": active_downloads,
        "last_successful_scan": last_scan.isoformat() if isinstance(last_scan, datetime) else None,
    }


@router.get("/savings-history")
async def get_savings_history(days: int = 30, user=Depends(get_current_user)):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session() as db:
        result = await db.execute(
            select(ActivityLog)
            .where(
                and_(
                    ActivityLog.event == "replace:completed",
                    ActivityLog.created_at >= cutoff,
                )
            )
            .order_by(ActivityLog.created_at.asc())
        )
        logs = result.scalars().all()

    # Build a cumulative series so the chart shows total reclaimed over time
    running_total = 0
    series = []
    for log in logs:
        running_total += log.savings_bytes or 0
        series.append({
            "date": log.created_at.isoformat(),
            "movie_title": log.movie_title,
            "savings_bytes": log.savings_bytes,
            "savings_pct": log.savings_pct,
            "cumulative_bytes": running_total,
        })
    return series


@router.get("/recent-activity")
async def get_recent_activity(limit: int = 20, user=Depends(get_current_user)):
    async with async_session() as db:
        result = await db.execute(
            select(ActivityLog)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
        )
        logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "event": log.event,
            "movie_title": log.movie_title,
            "savings_bytes": log.savings_bytes,
            "savings_pct": log.savings_pct,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
