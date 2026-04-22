"""Activity log API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from backend.auth.dependencies import get_current_user
from backend.database import ActivityLog, async_session

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("")
async def list_activity(
    page: int = 1,
    per_page: int = 50,
    event: str = "",
    user=Depends(get_current_user),
):
    per_page = min(per_page, 200)

    async with async_session() as db:
        query = select(ActivityLog)
        if event:
            query = query.where(ActivityLog.event == event)

        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_result.scalar_one()

        query = query.order_by(ActivityLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        logs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "activity": [
            {
                "id": log.id,
                "event": log.event,
                "movie_id": log.movie_id,
                "movie_title": log.movie_title,
                "old_file_path": log.old_file_path,
                "new_file_path": log.new_file_path,
                "old_size": log.old_size,
                "new_size": log.new_size,
                "savings_bytes": log.savings_bytes,
                "savings_pct": log.savings_pct,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }
