"""Persistent in-process job runtime for long-running Slimarr work."""
from __future__ import annotations

import asyncio
import contextvars
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select

from backend.database import JobEvent, JobRecord, async_session

ACTIVE_JOB_STATUSES = {"queued", "running", "cancelling"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled", "recovery_required"}

_running_tasks: dict[str, asyncio.Task] = {}
_running_tasks_guard = asyncio.Lock()
_current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "slimarr_current_job_id",
    default=None,
)


def get_current_job_id() -> str | None:
    return _current_job_id.get()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _encode_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _decode_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _job_payload(job: JobRecord, *, include_payload: bool = True) -> dict[str, Any]:
    payload = {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "priority": int(job.priority or 0),
        "progress_current": int(job.progress_current or 0),
        "progress_total": int(job.progress_total or 0),
        "heartbeat_at": job.heartbeat_at.isoformat() if job.heartbeat_at else None,
        "attempt": int(job.attempt or 0),
        "max_attempts": int(job.max_attempts or 0),
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "cancel_requested_at": job.cancel_requested_at.isoformat() if job.cancel_requested_at else None,
    }
    if include_payload:
        payload["payload"] = _decode_json(job.payload)
    return payload


def _event_payload(event: JobEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "job_id": event.job_id,
        "event": event.event,
        "message": event.message,
        "details": _decode_json(event.details),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


async def _add_event(
    session,
    job_id: str,
    event: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        JobEvent(
            job_id=job_id,
            event=event,
            message=message,
            details=_encode_json(details or {}),
            created_at=_utc_now(),
        )
    )


async def _execute_job_kind(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind == "manual_scan":
        from backend.core.scanner import scan_library

        await scan_library()
        return {"status": "scan_completed"}

    if kind == "full_cycle":
        from backend.core.orchestrator import run_full_cycle

        await run_full_cycle()
        return {"status": "cycle_completed"}

    if kind == "duplicate_preview":
        from backend.api.system import _duplicate_preview_cached

        result = await _duplicate_preview_cached(
            force=bool(payload.get("force", False)),
            max_movies_per_section=int(payload.get("max_movies_per_section") or 500),
            allow_scan=bool(payload.get("allow_scan", True)),
        )
        return {
            "status": result.get("status"),
            "movies_scanned": result.get("movies_scanned"),
            "duplicates_found": result.get("duplicates_found"),
            "estimated_reclaimable_bytes": result.get("estimated_reclaimable_bytes"),
            "truncated": result.get("truncated"),
        }

    if kind == "duplicate_cleanup":
        from backend.core.cleanup import scan_and_clean_duplicates

        await scan_and_clean_duplicates()
        return {"status": "cleanup_completed"}

    if kind == "recommendation_refresh":
        from backend.core.recommendations.engine import run_recommendation_refresh

        return await run_recommendation_refresh(
            max_movies=int(payload.get("max_movies") or 200),
        )

    if kind == "scheduler_task":
        from backend.scheduler.scheduler import get_scheduler

        task_id = str(payload.get("task_id") or "")
        job = get_scheduler().get_job(task_id)
        if not job:
            raise ValueError(f"Scheduled task '{task_id}' no longer exists")
        result = job.func()
        if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
            await result
        return {"status": "task_completed", "task_id": task_id}

    raise ValueError(f"Unsupported job kind: {kind}")


async def _heartbeat_loop(job_id: str, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            async with async_session() as session:
                job = await session.get(JobRecord, job_id)
                if job is None or job.status not in {"running", "cancelling"}:
                    return
                job.heartbeat_at = _utc_now()
                await session.commit()
        except Exception as exc:
            logger.debug("Job heartbeat failed for {}: {}", job_id, exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            continue


async def _run_job(job_id: str) -> None:
    stop_heartbeat = asyncio.Event()
    heartbeat_task: asyncio.Task | None = None
    token = _current_job_id.set(job_id)
    try:
        async with async_session() as session:
            job = await session.get(JobRecord, job_id)
            if job is None:
                return
            if job.status not in {"queued", "running"}:
                return
            now = _utc_now()
            job.status = "running"
            job.started_at = job.started_at or now
            job.heartbeat_at = now
            job.attempt = int(job.attempt or 0) + 1
            job.error_message = None
            await _add_event(session, job.id, "started", f"Started {job.kind}")
            payload = _decode_json(job.payload)
            kind = job.kind
            await session.commit()

        heartbeat_task = asyncio.create_task(_heartbeat_loop(job_id, stop_heartbeat))
        result = await _execute_job_kind(kind, payload)

        async with async_session() as session:
            job = await session.get(JobRecord, job_id)
            if job is None:
                return
            now = _utc_now()
            if job.cancel_requested_at:
                job.status = "cancelled"
                event = "cancelled"
                message = f"Cancelled {job.kind}"
            else:
                job.status = "completed"
                job.progress_current = max(int(job.progress_current or 0), int(job.progress_total or 1))
                event = "completed"
                message = f"Completed {job.kind}"
            job.completed_at = now
            job.heartbeat_at = now
            await _add_event(session, job.id, event, message, result)
            await session.commit()

    except asyncio.CancelledError:
        async with async_session() as session:
            job = await session.get(JobRecord, job_id)
            if job is not None:
                now = _utc_now()
                job.status = "cancelled"
                job.completed_at = now
                job.heartbeat_at = now
                await _add_event(session, job.id, "cancelled", f"Cancelled {job.kind}")
                await session.commit()
        raise
    except Exception as exc:
        logger.warning("Job {} failed: {}", job_id, exc)
        async with async_session() as session:
            job = await session.get(JobRecord, job_id)
            if job is not None:
                now = _utc_now()
                job.status = "failed"
                job.error_message = str(exc)
                job.completed_at = now
                job.heartbeat_at = now
                await _add_event(
                    session,
                    job.id,
                    "failed",
                    f"Failed {job.kind}",
                    {"error": str(exc)},
                )
                await session.commit()
    finally:
        stop_heartbeat.set()
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        _current_job_id.reset(token)
        async with _running_tasks_guard:
            _running_tasks.pop(job_id, None)


async def start_job(job_id: str) -> None:
    async with _running_tasks_guard:
        task = _running_tasks.get(job_id)
        if task and not task.done():
            return
        _running_tasks[job_id] = asyncio.create_task(_run_job(job_id))


async def enqueue_job(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 100,
    max_attempts: int = 1,
    singleton: bool = True,
    start: bool = True,
) -> dict[str, Any]:
    payload = payload or {}
    async with async_session() as session:
        if singleton:
            existing = (
                await session.execute(
                    select(JobRecord)
                    .where(JobRecord.kind == kind, JobRecord.status.in_(ACTIVE_JOB_STATUSES))
                    .order_by(JobRecord.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return {
                    "started": False,
                    "already_running": True,
                    "job": _job_payload(existing),
                }

        job = JobRecord(
            id=str(uuid.uuid4()),
            kind=kind,
            status="queued",
            priority=max(0, int(priority or 0)),
            payload=_encode_json(payload),
            progress_current=0,
            progress_total=1,
            attempt=0,
            max_attempts=max(1, int(max_attempts or 1)),
            created_at=_utc_now(),
        )
        session.add(job)
        await session.flush()
        await _add_event(session, job.id, "queued", f"Queued {kind}", payload)
        await session.commit()
        response = {"started": True, "already_running": False, "job": _job_payload(job)}

    if start:
        await start_job(str(response["job"]["id"]))
    return response


async def list_persistent_jobs(
    *,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    async with async_session() as session:
        query = select(JobRecord)
        if status and status != "all":
            if status == "active":
                query = query.where(JobRecord.status.in_(ACTIVE_JOB_STATUSES))
            else:
                query = query.where(JobRecord.status == status)
        if kind:
            query = query.where(JobRecord.kind == kind)
        rows = (
            await session.execute(
                query.order_by(JobRecord.created_at.desc()).limit(max(1, min(200, int(limit or 50))))
            )
        ).scalars().all()

    return {
        "jobs": [_job_payload(job) for job in rows],
        "active_statuses": sorted(ACTIVE_JOB_STATUSES),
    }


async def get_persistent_job(job_id: str) -> dict[str, Any] | None:
    async with async_session() as session:
        job = await session.get(JobRecord, job_id)
        if job is None:
            return None
        events = (
            await session.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.created_at.asc(), JobEvent.id.asc())
            )
        ).scalars().all()

    payload = _job_payload(job)
    payload["events"] = [_event_payload(event) for event in events]
    return payload


async def cancel_job(job_id: str) -> dict[str, Any] | None:
    async with async_session() as session:
        job = await session.get(JobRecord, job_id)
        if job is None:
            return None
        if job.status in TERMINAL_JOB_STATUSES:
            return _job_payload(job)
        now = _utc_now()
        job.cancel_requested_at = now
        job.status = "cancelling" if job.status == "running" else "cancelled"
        if job.status == "cancelled":
            job.completed_at = now
        await _add_event(session, job.id, "cancel_requested", f"Cancel requested for {job.kind}")
        await session.commit()
        payload = _job_payload(job)

    async with _running_tasks_guard:
        task = _running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
    return payload


async def retry_job(job_id: str) -> dict[str, Any] | None:
    async with async_session() as session:
        job = await session.get(JobRecord, job_id)
        if job is None:
            return None
        if job.status not in TERMINAL_JOB_STATUSES:
            return {
                "started": False,
                "already_running": True,
                "job": _job_payload(job),
            }
        payload = _decode_json(job.payload)
        kind = job.kind
        priority = int(job.priority or 100)
        max_attempts = int(job.max_attempts or 1)
    return await enqueue_job(
        kind,
        payload,
        priority=priority,
        max_attempts=max_attempts,
        singleton=False,
        start=True,
    )


async def recover_stale_jobs() -> int:
    async with async_session() as session:
        rows = (
            await session.execute(
                select(JobRecord).where(JobRecord.status.in_(["running", "cancelling"]))
            )
        ).scalars().all()
        now = _utc_now()
        for job in rows:
            job.status = "recovery_required"
            job.completed_at = now
            job.heartbeat_at = now
            job.error_message = "Process restarted while job was active"
            await _add_event(
                session,
                job.id,
                "recovery_required",
                "Process restarted while job was active",
            )
        await session.commit()
        return len(rows)


async def purge_old_jobs(keep_days: int = 30) -> int:
    """Delete terminal jobs (and their events via cascade) completed more than keep_days ago.

    Only terminal statuses (completed, failed, cancelled, recovery_required) are
    eligible. Active jobs are never removed.
    """
    from sqlalchemy import delete

    cutoff = _utc_now() - timedelta(days=max(1, int(keep_days)))
    try:
        async with async_session() as session:
            result = await session.execute(
                delete(JobRecord).where(
                    JobRecord.status.in_(TERMINAL_JOB_STATUSES),
                    JobRecord.completed_at < cutoff,
                )
            )
            await session.commit()
            count = int(result.rowcount or 0)
        if count:
            logger.info("Purged {} terminal job record(s) older than {} days", count, keep_days)
        return count
    except Exception as exc:
        logger.warning("Failed to purge old job records: {}", exc)
        return 0
