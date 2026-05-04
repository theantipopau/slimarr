"""Audit event helpers for auth/settings/security activities."""
from __future__ import annotations

import json
from typing import Any

from backend.database import ActivityLog, async_session


async def log_audit_event(event: str, actor: str | None = None, details: dict[str, Any] | None = None) -> None:
    """Persist a system-level audit event in activity_log."""
    payload = json.dumps(details or {}, ensure_ascii=True)
    async with async_session() as db:
        db.add(
            ActivityLog(
                event=event,
                actor=actor,
                details=payload,
                movie_id=None,
                movie_title=None,
            )
        )
        await db.commit()
