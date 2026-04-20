"""Dashboard API routes."""
from __future__ import annotations

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

        savings_row = await db.execute(
            select(func.sum(ActivityLog.savings_bytes)).where(
                ActivityLog.event == "replace:completed"
            )
        )
        total_savings = savings_row.scalar_one() or 0

        active_downloads = (await db.execute(
            select(func.count()).select_from(Download).where(
                Download.status == "downloading"
            )
        )).scalar_one()

    return {
        "total_movies": total_movies,
        "improved": improved,
        "pending": total_movies - improved,
        "total_savings_bytes": total_savings,
        "active_downloads": active_downloads,
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

    return [
        {
            "date": log.created_at.isoformat(),
            "movie_title": log.movie_title,
            "savings_bytes": log.savings_bytes,
            "savings_pct": log.savings_pct,
        }
        for log in logs
    ]


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
