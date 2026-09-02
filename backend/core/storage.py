"""Storage path helpers for NAS-aware safety decisions."""
from __future__ import annotations

import os
import posixpath
import shutil
import asyncio
import time
import json
import uuid
from contextlib import asynccontextmanager
from collections import Counter, deque
from dataclasses import dataclass
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

_operation_locks: dict[str, asyncio.Lock] = {}
_operation_locks_guard = asyncio.Lock()
_operation_history: deque[dict[str, Any]] = deque(maxlen=250)
_operation_counters: Counter[str] = Counter()
_nas_policy_guard = asyncio.Lock()
_nas_active_operations = 0
_nas_cooldown_until = 0.0
_nas_last_failure: dict[str, Any] | None = None
_nas_reserved_write_bytes = 0
_nas_reserved_replacements = 0
_nas_persisted_usage_cache = {"write_bytes": 0, "replacements": 0}


class StoragePolicyBlocked(OSError):
    """Raised when a configured NAS safety budget blocks an operation."""


@dataclass(frozen=True)
class StoragePathInfo:
    path: str
    normalized_path: str
    classification: str
    matched_prefix: str | None = None


@dataclass(frozen=True)
class StoragePreflight:
    purpose: str
    path: str
    classification: str
    matched_prefix: str | None
    exists: bool
    parent_path: str | None
    parent_exists: bool
    free_bytes: int | None
    required_bytes: int
    status: str
    messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "path": self.path,
            "classification": self.classification,
            "matched_prefix": self.matched_prefix,
            "exists": self.exists,
            "parent_path": self.parent_path,
            "parent_exists": self.parent_exists,
            "free_bytes": self.free_bytes,
            "required_bytes": self.required_bytes,
            "status": self.status,
            "messages": self.messages,
        }


@dataclass(frozen=True)
class StorageOperationResult:
    operation: str
    purpose: str
    source_path: str
    target_path: str | None
    source_classification: str
    target_classification: str | None
    status: str
    bytes_estimated: int
    messages: list[str]
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: float | None = None
    job_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "purpose": self.purpose,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "source_classification": self.source_classification,
            "target_classification": self.target_classification,
            "status": self.status,
            "bytes_estimated": self.bytes_estimated,
            "messages": self.messages,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "job_id": self.job_id,
        }


def normalize_path(path: str | None) -> str:
    """Normalize a path for prefix comparisons without changing the real path.

    Collapses "." / ".." segments so an embedded traversal (e.g.
    "/mnt/local/../nas/movies") can't evade NAS-prefix classification by
    presenting differently than its resolved form, and only folds case on
    platforms where the filesystem is actually case-insensitive (Windows) -
    on case-sensitive Linux/NFS mounts, two differently-cased paths are
    genuinely different locations and must not be treated as the same one.
    A relative path that still escapes above its own root after collapsing
    (e.g. "../secret") is left as-is; it then simply won't match any
    configured (absolute) prefix, which fails closed rather than open.
    """
    text = str(path or "").replace("\\", "/").strip()
    if not text:
        return ""
    collapsed = posixpath.normpath(text)
    if collapsed == ".":
        return ""
    if os.name == "nt":
        collapsed = collapsed.lower()
    return collapsed.rstrip("/")


def path_matches_prefix(path: str | None, prefixes: list[str] | tuple[str, ...]) -> bool:
    norm = normalize_path(path)
    if not norm:
        return False
    for prefix in prefixes:
        check = normalize_path(prefix)
        if not check:
            continue
        if norm == check or norm.startswith(check + "/"):
            return True
    return False


def matched_prefix(path: str | None, prefixes: list[str] | tuple[str, ...]) -> str | None:
    norm = normalize_path(path)
    if not norm:
        return None
    for prefix in prefixes:
        check = normalize_path(prefix)
        if not check:
            continue
        if norm == check or norm.startswith(check + "/"):
            return str(prefix)
    return None


def configured_nas_prefixes(config: Any) -> list[str]:
    files = getattr(config, "files", None)
    prefixes = getattr(files, "nas_path_prefixes", []) or []
    return [str(prefix).strip() for prefix in prefixes if str(prefix or "").strip()]


def is_nas_path(path: str | None, config_or_prefixes: Any) -> bool:
    if isinstance(config_or_prefixes, (list, tuple)):
        prefixes = list(config_or_prefixes)
    else:
        prefixes = configured_nas_prefixes(config_or_prefixes)
    return path_matches_prefix(path, prefixes)


def classify_storage_path(path: str | None, config: Any) -> StoragePathInfo:
    text = str(path or "").strip()
    norm = normalize_path(text)
    files = getattr(config, "files", None)
    nas_prefixes = configured_nas_prefixes(config)
    recycle_path = str(getattr(files, "recycling_bin", "") or "").strip()

    nas_match = matched_prefix(text, nas_prefixes)
    if nas_match:
        return StoragePathInfo(text, norm, "nas", nas_match)

    if recycle_path and path_matches_prefix(text, [recycle_path]):
        return StoragePathInfo(text, norm, "recycling", recycle_path)

    if norm.startswith("//"):
        return StoragePathInfo(text, norm, "network")

    if not norm:
        return StoragePathInfo(text, norm, "unknown")

    return StoragePathInfo(text, norm, "local")


def _find_existing_parent(path: str) -> str | None:
    if not path:
        return None
    current = os.path.abspath(path)
    while current and not os.path.exists(current):
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return current if os.path.exists(current) else None


def preflight_storage_path(
    path: str | None,
    config: Any,
    *,
    required_bytes: int = 0,
    purpose: str = "storage_path",
) -> StoragePreflight:
    text = str(path or "").strip()
    info = classify_storage_path(text, config)
    messages: list[str] = []
    status = "ok"

    if not text:
        return StoragePreflight(
            purpose=purpose,
            path="",
            classification="unknown",
            matched_prefix=None,
            exists=False,
            parent_path=None,
            parent_exists=False,
            free_bytes=None,
            required_bytes=max(0, int(required_bytes or 0)),
            status="block",
            messages=["Path is empty"],
        )

    exists = os.path.exists(text)
    parent_path = text if os.path.isdir(text) else os.path.dirname(text)
    existing_parent = _find_existing_parent(parent_path or text)
    parent_exists = existing_parent is not None
    free_bytes: int | None = None

    if not parent_exists:
        status = "block"
        messages.append("No accessible parent path found")
    else:
        try:
            free_bytes = int(shutil.disk_usage(existing_parent).free)
        except Exception as exc:
            status = "warn"
            messages.append(f"Could not read disk usage: {exc}")

    needed = max(0, int(required_bytes or 0))
    if free_bytes is not None and needed > 0 and free_bytes < needed:
        status = "block"
        messages.append(
            f"Insufficient free space: {free_bytes:,} bytes available, {needed:,} required"
        )

    if info.classification in {"nas", "network"}:
        messages.append("Network/NAS path detected; storage operation should use NAS-safe pacing")

    if not exists:
        messages.append("Path does not currently exist")

    return StoragePreflight(
        purpose=purpose,
        path=text,
        classification=info.classification,
        matched_prefix=info.matched_prefix,
        exists=exists,
        parent_path=existing_parent,
        parent_exists=parent_exists,
        free_bytes=free_bytes,
        required_bytes=needed,
        status=status,
        messages=messages,
    )


def _estimated_path_bytes(path: str) -> int:
    try:
        if os.path.isfile(path):
            return int(os.path.getsize(path))
        if os.path.isdir(path):
            total = 0
            for root, _, files in os.walk(path):
                for name in files:
                    try:
                        total += int(os.path.getsize(os.path.join(root, name)))
                    except OSError:
                        continue
            return total
    except OSError:
        return 0
    return 0


def _same_storage_device(source: str, target: str) -> bool:
    """Best-effort check for whether a move can be a metadata-only rename."""
    try:
        target_parent = _find_existing_parent(os.path.dirname(target) or target)
        if not target_parent:
            return False
        return os.stat(source).st_dev == os.stat(target_parent).st_dev
    except OSError:
        return False


def _copy_file_throttled(source: str, target: str, config: Any) -> bool:
    """Copy a file through a temporary target with optional NAS rate limiting.

    Returns True if the source was also removed after a successful copy,
    or False if the copy/replace succeeded but the source could not be
    removed afterwards. The latter is deliberately NOT raised as a
    failure: the target already has a complete, correct copy at that
    point, so reporting it as a failed move would be wrong and could
    trigger a caller to retry the whole copy again on top of an already-
    good target. It leaves a duplicate at `source` that needs manual
    cleanup instead.
    """
    files = getattr(config, "files", None)
    chunk_mb = max(1, int(getattr(files, "nas_copy_chunk_mb", 8) or 8))
    max_mbps = max(0.0, float(getattr(files, "nas_max_transfer_mbps", 50.0) or 0.0))
    chunk_bytes = chunk_mb * 1024 * 1024
    bytes_per_second = max_mbps * 1024 * 1024
    temporary = f"{target}.slimarr-{uuid.uuid4().hex}.part"
    copied = 0
    started = time.monotonic()
    try:
        with open(source, "rb", buffering=0) as source_file:
            with open(temporary, "xb", buffering=0) as target_file:
                while True:
                    block = source_file.read(chunk_bytes)
                    if not block:
                        break
                    target_file.write(block)
                    copied += len(block)
                    if bytes_per_second > 0:
                        expected_seconds = copied / bytes_per_second
                        delay = expected_seconds - (time.monotonic() - started)
                        if delay > 0:
                            time.sleep(delay)
        shutil.copystat(source, temporary)
        if os.path.exists(target):
            raise FileExistsError(f"Refusing to overwrite existing target: {target}")
        os.replace(temporary, target)
    except Exception:
        try:
            os.remove(temporary)
        except OSError:
            pass
        raise

    try:
        os.remove(source)
        return True
    except OSError as exc:
        logger.warning(
            "Copy to {} succeeded but the source {} could not be removed ({}); "
            "a duplicate now exists at the source path and needs manual cleanup.",
            target,
            source,
            exc,
        )
        return False


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_path(path: str | None) -> str | None:
    if not path:
        return path
    text = str(path)
    drive, tail = os.path.splitdrive(text)
    parent, name = os.path.split(tail)
    if not name:
        name = parent.strip("\\/") or tail
    if drive:
        return os.path.join(drive + os.sep, "...", name)
    if text.startswith(("\\\\", "//")):
        return os.path.join("//...", name)
    if text.startswith(("/", "\\")):
        return os.path.join(os.sep, "...", name)
    return os.path.join("...", name)


def nas_policy_snapshot(*, redact_paths: bool = False) -> dict[str, Any]:
    """Return in-memory NAS safety policy state."""
    now = time.monotonic()
    last_failure = dict(_nas_last_failure or {})
    if redact_paths and last_failure:
        last_failure["path"] = _redact_path(last_failure.get("path"))
        last_failure["target_path"] = _redact_path(last_failure.get("target_path"))
    return {
        "active_operations": _nas_active_operations,
        "cooldown_active": _nas_cooldown_until > now,
        "cooldown_remaining_seconds": max(0, int(_nas_cooldown_until - now)),
        "last_failure": last_failure or None,
        "write_bytes_used_24h": max(
            _nas_write_bytes_used_24h(),
            int(_nas_persisted_usage_cache.get("write_bytes", 0)),
        ),
        "replacements_24h": max(
            _nas_replacements_24h(),
            int(_nas_persisted_usage_cache.get("replacements", 0)),
        ),
        "reserved_write_bytes": _nas_reserved_write_bytes,
        "reserved_replacements": _nas_reserved_replacements,
    }


def _record_operation(result: StorageOperationResult) -> None:
    payload = result.to_dict()
    _operation_history.appendleft(payload)
    prefix = f"{result.operation}:{result.status}"
    _operation_counters[prefix] += 1
    _operation_counters[f"{result.operation}:total"] += 1
    _operation_counters[f"classification:{result.source_classification}:{result.status}"] += 1
    if result.target_classification:
        _operation_counters[f"target_classification:{result.target_classification}:{result.status}"] += 1
    if result.status == "completed":
        _operation_counters[f"{result.operation}:bytes_estimated"] += int(result.bytes_estimated or 0)


def _history_timestamp(item: dict[str, Any]) -> float | None:
    raw = item.get("completed_at") or item.get("started_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _path_health_key(result: StorageOperationResult) -> tuple[str, str] | None:
    if result.source_classification in {"nas", "network"}:
        return result.source_path, result.source_classification
    if result.target_path and result.target_classification in {"nas", "network"}:
        return result.target_path, result.target_classification or "network"
    return None


async def _persist_operation(result: StorageOperationResult) -> None:
    try:
        from sqlalchemy import select

        from backend.database import StorageOperationLog, StoragePathHealth, async_session

        started_at = _parse_iso_datetime(result.started_at)
        completed_at = _parse_iso_datetime(result.completed_at)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with async_session() as session:
            session.add(
                StorageOperationLog(
                    operation_type=result.operation,
                    purpose=result.purpose,
                    source_path=result.source_path,
                    target_path=result.target_path,
                    source_classification=result.source_classification,
                    target_classification=result.target_classification,
                    estimated_bytes=max(0, int(result.bytes_estimated or 0)),
                    actual_bytes=max(0, int(result.bytes_estimated or 0)) if result.status == "completed" else None,
                    status=result.status,
                    error_message=result.error,
                    messages=json.dumps(result.messages or []),
                    duration_ms=result.duration_ms,
                    job_id=result.job_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    created_at=completed_at or started_at or now,
                )
            )

            health_key = _path_health_key(result)
            if health_key:
                prefix, classification = health_key
                existing = (
                    await session.execute(
                        select(StoragePathHealth).where(StoragePathHealth.path_prefix == prefix)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    existing = StoragePathHealth(
                        path_prefix=prefix,
                        classification=classification,
                    )
                    session.add(existing)
                existing.classification = classification
                existing.updated_at = now
                if result.status == "failed":
                    existing.last_failure_at = completed_at or now
                    existing.failure_count = int(existing.failure_count or 0) + 1
                    existing.last_error_message = result.error
                    if _nas_cooldown_until > time.monotonic():
                        cooldown_seconds = max(0, int(_nas_cooldown_until - time.monotonic()))
                        existing.cooldown_until = datetime.fromtimestamp(
                            time.time() + cooldown_seconds,
                            tz=timezone.utc,
                        ).replace(tzinfo=None)
                elif result.status == "completed":
                    existing.last_success_at = completed_at or now
                    existing.cooldown_until = None
                    existing.last_error_message = None

            await session.commit()
    except Exception as exc:
        logger.warning(
            "Storage operation persistence failed: purpose={} operation={} status={} error={}",
            result.purpose,
            result.operation,
            result.status,
            exc,
        )


async def restore_nas_cooldown_state() -> None:
    """Re-arm any NAS failure cooldown that was still active when the
    process last stopped.

    _nas_cooldown_until is a time.monotonic() value and unconditionally
    resets to 0 on restart - without this, a restart immediately after a
    NAS failure silently drops the cooldown and the very next replacement
    can hit the same failing share right away (see F5 in
    docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md). Called once from the
    FastAPI lifespan, after init_db(), mirroring recover_stale_jobs().
    """
    global _nas_cooldown_until, _nas_last_failure
    try:
        from sqlalchemy import select

        from backend.database import StoragePathHealth, async_session

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(StoragePathHealth).where(StoragePathHealth.cooldown_until.is_not(None))
                )
            ).scalars().all()

        active = [row for row in rows if row.cooldown_until and row.cooldown_until > now_utc]
        if not active:
            return

        latest = max(active, key=lambda row: row.cooldown_until)
        remaining_seconds = (latest.cooldown_until - now_utc).total_seconds()
        async with _nas_policy_guard:
            _nas_cooldown_until = time.monotonic() + remaining_seconds
            _nas_last_failure = {
                "operation": "restored",
                "purpose": "startup_restore",
                "path": latest.path_prefix,
                "target_path": None,
                "error": latest.last_error_message or "NAS cooldown restored from a prior failure",
                "at": _utc_iso(),
            }
        logger.warning(
            "Restored an active NAS failure cooldown from a previous run: {} more second(s) for {}",
            int(remaining_seconds),
            latest.path_prefix,
        )
    except Exception as exc:
        logger.warning("Failed to restore NAS cooldown state on startup: {}", exc)


def _history_since(seconds: float) -> list[dict[str, Any]]:
    cutoff = time.time() - max(0.0, seconds)
    return [
        item
        for item in list(_operation_history)
        if (_history_timestamp(item) or 0.0) >= cutoff
    ]


def _redacted_operation_payload(item: dict[str, Any], *, redact_paths: bool) -> dict[str, Any]:
    payload = dict(item)
    if redact_paths:
        payload["source_path"] = _redact_path(payload.get("source_path"))
        payload["target_path"] = _redact_path(payload.get("target_path"))
    return payload


def recent_storage_failures(
    *,
    seconds: float = 60 * 60,
    redact_paths: bool = False,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return failed storage operations inside a bounded recent window."""
    failures = [
        _redacted_operation_payload(item, redact_paths=redact_paths)
        for item in _history_since(seconds)
        if item.get("status") == "failed"
    ]
    return failures[: max(0, int(limit or 0))]


def _operation_row_to_payload(row: Any, *, redact_paths: bool = False) -> dict[str, Any]:
    messages: list[str] = []
    try:
        raw_messages = json.loads(row.messages or "[]")
        if isinstance(raw_messages, list):
            messages = [str(item) for item in raw_messages]
    except (TypeError, ValueError):
        messages = []

    payload = {
        "id": row.id,
        "operation": row.operation_type,
        "purpose": row.purpose,
        "source_path": row.source_path,
        "target_path": row.target_path,
        "source_classification": row.source_classification,
        "target_classification": row.target_classification,
        "status": row.status,
        "bytes_estimated": int(row.estimated_bytes or 0),
        "actual_bytes": row.actual_bytes,
        "messages": messages,
        "error": row.error_message,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "duration_ms": row.duration_ms,
        "job_id": row.job_id,
        "persisted": True,
    }
    if redact_paths:
        payload["source_path"] = _redact_path(payload.get("source_path"))
        payload["target_path"] = _redact_path(payload.get("target_path"))
    return payload


async def persisted_storage_operation_snapshot(
    *,
    redact_paths: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Return durable storage operation telemetry from the database."""
    try:
        from sqlalchemy import func, select

        from backend.database import StorageOperationLog, async_session

        capped_limit = max(0, min(500, int(limit or 0)))
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(StorageOperationLog)
                    .order_by(StorageOperationLog.created_at.desc(), StorageOperationLog.id.desc())
                    .limit(capped_limit)
                )
            ).scalars().all()
            status_rows = (
                await session.execute(
                    select(
                        StorageOperationLog.operation_type,
                        StorageOperationLog.status,
                        func.count(StorageOperationLog.id),
                    ).group_by(StorageOperationLog.operation_type, StorageOperationLog.status)
                )
            ).all()
            byte_rows = (
                await session.execute(
                    select(
                        StorageOperationLog.operation_type,
                        func.sum(StorageOperationLog.estimated_bytes),
                    )
                    .where(StorageOperationLog.status == "completed")
                    .group_by(StorageOperationLog.operation_type)
                )
            ).all()
            total = (
                await session.execute(
                    select(func.count()).select_from(StorageOperationLog)
                )
            ).scalar_one()

        counters: dict[str, int] = {}
        for operation, status, count in status_rows:
            counters[f"{operation}:{status}"] = int(count or 0)
            counters[f"{operation}:total"] = counters.get(f"{operation}:total", 0) + int(count or 0)
        for operation, total_bytes in byte_rows:
            counters[f"{operation}:bytes_estimated"] = int(total_bytes or 0)

        return {
            "recent": [
                _operation_row_to_payload(row, redact_paths=redact_paths)
                for row in rows
            ],
            "counters": counters,
            "history_size": int(total or 0),
            "available": True,
        }
    except Exception as exc:
        logger.debug("Persisted storage operation snapshot unavailable: {}", exc)
        return {
            "recent": [],
            "counters": {},
            "history_size": 0,
            "available": False,
            "error": str(exc),
        }


def _is_replacement_purpose(purpose: str) -> bool:
    return "replacement" in str(purpose or "").lower() or str(purpose or "") == "place_replacement"


def _nas_write_bytes_used_24h() -> int:
    total = 0
    for item in _history_since(24 * 60 * 60):
        if item.get("operation") != "move" or item.get("status") != "completed":
            continue
        if item.get("target_classification") not in {"nas", "network"}:
            continue
        total += int(item.get("bytes_estimated") or 0)
    return total


def _nas_replacements_24h() -> int:
    count = 0
    for item in _history_since(24 * 60 * 60):
        if item.get("operation") != "move" or item.get("status") != "completed":
            continue
        if item.get("target_classification") not in {"nas", "network"}:
            continue
        if _is_replacement_purpose(str(item.get("purpose") or "")):
            count += 1
    return count


async def _persisted_nas_usage_24h() -> tuple[int, int]:
    """Return durable NAS writes/replacements completed in the last 24 hours."""
    global _nas_persisted_usage_cache
    try:
        from sqlalchemy import func, or_, select

        from backend.database import StorageOperationLog, async_session

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
        completed_move = (
            (StorageOperationLog.operation_type == "move")
            & (StorageOperationLog.status == "completed")
            & StorageOperationLog.target_classification.in_(["nas", "network"])
            & (StorageOperationLog.completed_at >= cutoff)
        )
        async with async_session() as session:
            write_bytes = (
                await session.execute(
                    select(func.sum(StorageOperationLog.actual_bytes)).where(completed_move)
                )
            ).scalar_one() or 0
            replacements = (
                await session.execute(
                    select(func.count(StorageOperationLog.id)).where(
                        completed_move,
                        or_(
                            StorageOperationLog.purpose.ilike("%replacement%"),
                            StorageOperationLog.purpose == "place_replacement",
                        ),
                    )
                )
            ).scalar_one() or 0
        _nas_persisted_usage_cache = {
            "write_bytes": max(0, int(write_bytes)),
            "replacements": max(0, int(replacements)),
        }
    except Exception as exc:
        logger.debug("Persisted NAS usage unavailable; using in-memory counters: {}", exc)
    return (
        int(_nas_persisted_usage_cache.get("write_bytes", 0)),
        int(_nas_persisted_usage_cache.get("replacements", 0)),
    )


async def refresh_nas_policy_usage() -> dict[str, Any]:
    """Refresh durable 24-hour counters and return the current policy snapshot."""
    await _persisted_nas_usage_24h()
    return nas_policy_snapshot(redact_paths=True)


def _nas_policy_settings(config: Any) -> dict[str, Any]:
    files = getattr(config, "files", None)
    return {
        "max_write_bytes_per_24h": int(
            max(0.0, float(getattr(files, "nas_max_write_gb_per_day", 0.0) or 0.0)) * 1024 * 1024 * 1024
        ),
        "max_replacements_per_24h": max(0, int(getattr(files, "nas_max_replacements_per_day", 0) or 0)),
        "max_concurrent_operations": max(1, int(getattr(files, "nas_max_concurrent_operations", 1) or 1)),
        "failure_cooldown_seconds": max(0, int(getattr(files, "nas_failure_cooldown_minutes", 15) or 0)) * 60,
    }


def _operation_touches_nas(config: Any, source_path: str, target_path: str | None) -> bool:
    source_info = classify_storage_path(source_path, config)
    target_info = classify_storage_path(target_path, config) if target_path else None
    if source_info.classification in {"nas", "network"}:
        return True
    return bool(target_info and target_info.classification in {"nas", "network"})


@asynccontextmanager
async def _nas_policy_scope(
    *,
    operation: str,
    purpose: str,
    source_path: str,
    target_path: str | None,
    config: Any,
    estimated_bytes: int,
) -> AsyncIterator[None]:
    global _nas_active_operations, _nas_cooldown_until, _nas_last_failure
    global _nas_reserved_write_bytes, _nas_reserved_replacements

    if not _operation_touches_nas(config, source_path, target_path):
        yield
        return

    settings = _nas_policy_settings(config)
    reserved_write = 0
    reserved_replacement = 0
    async with _nas_policy_guard:
        now = time.monotonic()
        if _nas_cooldown_until > now:
            remaining = int(_nas_cooldown_until - now)
            _operation_counters["nas:cooldown_blocked"] += 1
            raise StoragePolicyBlocked(
                f"NAS storage cooldown is active for another {remaining} seconds"
            )

        if _nas_active_operations >= settings["max_concurrent_operations"]:
            _operation_counters["nas:concurrency_blocked"] += 1
            raise StoragePolicyBlocked(
                "NAS storage operation limit reached "
                f"({_nas_active_operations}/{settings['max_concurrent_operations']} active)"
            )

        # A same-directory rename (e.g. backup_existing_target's
        # "<file>.slimarr-old" step) is a metadata-only os.rename() that
        # moves zero bytes - billing it against the NAS write budget at
        # full file size can exhaust the daily cap on phantom writes alone
        # and fail every genuine replacement behind it. _same_storage_device
        # already exists and is used to choose rename over throttled copy at
        # the execution site (see move_path below); reuse it here so the
        # accounting path agrees with the execution path.
        same_device = bool(source_path and target_path and _same_storage_device(source_path, target_path))
        if operation == "move" and target_path and not same_device:
            target_info = classify_storage_path(target_path, config)
            if target_info.classification in {"nas", "network"}:
                persisted_write, persisted_replacements = await _persisted_nas_usage_24h()
                max_write = int(settings["max_write_bytes_per_24h"])
                if max_write > 0:
                    used = max(_nas_write_bytes_used_24h(), persisted_write)
                    requested = max(0, int(estimated_bytes or 0))
                    if used + _nas_reserved_write_bytes + requested > max_write:
                        _operation_counters["nas:write_budget_blocked"] += 1
                        raise StoragePolicyBlocked(
                            "NAS daily write budget would be exceeded "
                            f"({used:,} used, {_nas_reserved_write_bytes:,} reserved, "
                            f"{requested:,} requested, {max_write:,} limit)"
                        )
                    reserved_write = requested

                max_replacements = int(settings["max_replacements_per_24h"])
                if max_replacements > 0 and _is_replacement_purpose(purpose):
                    used_replacements = max(_nas_replacements_24h(), persisted_replacements)
                    if used_replacements + _nas_reserved_replacements + 1 > max_replacements:
                        _operation_counters["nas:replacement_budget_blocked"] += 1
                        raise StoragePolicyBlocked(
                            "NAS daily replacement budget would be exceeded "
                            f"({used_replacements} used, {_nas_reserved_replacements} reserved, "
                            f"{max_replacements} limit)"
                        )
                    reserved_replacement = 1

        _nas_active_operations += 1
        _nas_reserved_write_bytes += reserved_write
        _nas_reserved_replacements += reserved_replacement
        _operation_counters["nas:operations_started"] += 1

    try:
        yield
    except Exception as exc:
        if not isinstance(exc, StoragePolicyBlocked) and settings["failure_cooldown_seconds"] > 0:
            async with _nas_policy_guard:
                _nas_cooldown_until = max(
                    _nas_cooldown_until,
                    time.monotonic() + float(settings["failure_cooldown_seconds"]),
                )
                _nas_last_failure = {
                    "operation": operation,
                    "purpose": purpose,
                    "path": source_path,
                    "target_path": target_path,
                    "error": str(exc),
                    "at": _utc_iso(),
                }
                _operation_counters["nas:cooldowns_started"] += 1
        raise
    finally:
        async with _nas_policy_guard:
            _nas_active_operations = max(0, _nas_active_operations - 1)
            _nas_reserved_write_bytes = max(0, _nas_reserved_write_bytes - reserved_write)
            _nas_reserved_replacements = max(0, _nas_reserved_replacements - reserved_replacement)


def _operation_result_with_timing(
    result: StorageOperationResult,
    *,
    started_at: str,
    completed_at: str,
    started_monotonic: float,
) -> StorageOperationResult:
    from backend.core.jobs import get_current_job_id

    return StorageOperationResult(
        operation=result.operation,
        purpose=result.purpose,
        source_path=result.source_path,
        target_path=result.target_path,
        source_classification=result.source_classification,
        target_classification=result.target_classification,
        status=result.status,
        bytes_estimated=result.bytes_estimated,
        messages=result.messages,
        error=result.error,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=round((time.monotonic() - started_monotonic) * 1000, 2),
        job_id=result.job_id or get_current_job_id(),
    )


def _failed_operation_result(
    *,
    operation: str,
    purpose: str,
    source_path: str,
    target_path: str | None,
    config: Any,
    started_at: str,
    started_monotonic: float,
    error: Exception,
    bytes_estimated: int = 0,
) -> StorageOperationResult:
    from backend.core.jobs import get_current_job_id

    source_info = classify_storage_path(source_path, config)
    target_info = classify_storage_path(target_path, config) if target_path else None
    result = StorageOperationResult(
        operation=operation,
        purpose=purpose,
        source_path=source_path,
        target_path=target_path,
        source_classification=source_info.classification,
        target_classification=target_info.classification if target_info else None,
        status="failed",
        bytes_estimated=max(0, int(bytes_estimated or 0)),
        messages=[],
        error=str(error),
        started_at=started_at,
        completed_at=_utc_iso(),
        duration_ms=round((time.monotonic() - started_monotonic) * 1000, 2),
        job_id=get_current_job_id(),
    )
    return result


def storage_operation_snapshot(*, redact_paths: bool = False, limit: int = 50) -> dict[str, Any]:
    """Return recent storage operation telemetry for diagnostics and UI summaries."""
    recent = []
    for item in list(_operation_history)[: max(0, int(limit or 0))]:
        recent.append(_redacted_operation_payload(item, redact_paths=redact_paths))

    return {
        "recent": recent,
        "recent_failures": recent_storage_failures(
            seconds=60 * 60,
            redact_paths=redact_paths,
            limit=max(10, min(50, int(limit or 0))),
        ),
        "recent_failure_window_seconds": 60 * 60,
        "counters": dict(_operation_counters),
        "history_size": len(_operation_history),
        "nas_policy": nas_policy_snapshot(redact_paths=redact_paths),
    }


def storage_operation_metrics() -> dict[str, int]:
    return dict(_operation_counters)


def reset_storage_operation_telemetry() -> None:
    global _nas_active_operations, _nas_cooldown_until, _nas_last_failure
    global _nas_reserved_write_bytes, _nas_reserved_replacements, _nas_persisted_usage_cache
    _operation_history.clear()
    _operation_counters.clear()
    _nas_active_operations = 0
    _nas_cooldown_until = 0.0
    _nas_last_failure = None
    _nas_reserved_write_bytes = 0
    _nas_reserved_replacements = 0
    _nas_persisted_usage_cache = {"write_bytes": 0, "replacements": 0}


async def purge_old_storage_operations(keep_days: int = 30) -> int:
    """Delete persisted storage_operations records older than keep_days.

    In-memory telemetry is not affected; only the durable DB log is trimmed.
    """
    try:
        from sqlalchemy import delete

        from backend.database import StorageOperationLog
        from backend.database import async_session as _async_session

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=max(1, int(keep_days)))
        async with _async_session() as session:
            result = await session.execute(
                delete(StorageOperationLog).where(StorageOperationLog.created_at < cutoff)
            )
            await session.commit()
            count = int(result.rowcount or 0)
        if count:
            logger.info(
                "Purged {} persisted storage operation record(s) older than {} days",
                count,
                keep_days,
            )
        return count
    except Exception as exc:
        logger.warning("Failed to purge old storage operation records: {}", exc)
        return 0


@asynccontextmanager
async def _storage_operation_lock(paths: list[str]) -> AsyncIterator[None]:
    keys = sorted({normalize_path(path) for path in paths if normalize_path(path)})
    async with _operation_locks_guard:
        locks = [_operation_locks.setdefault(key, asyncio.Lock()) for key in keys]

    for lock in locks:
        await lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()


def _move_path_sync(
    source: str,
    target: str,
    config: Any,
    purpose: str,
    required_bytes: int | None,
    estimated_bytes: int,
) -> StorageOperationResult:
    source_info = classify_storage_path(source, config)
    target_info = classify_storage_path(target, config)
    bytes_required = estimated_bytes if required_bytes is None else max(0, int(required_bytes or 0))
    preflight = preflight_storage_path(
        target,
        config,
        required_bytes=bytes_required,
        purpose=purpose,
    )
    messages = list(preflight.messages)
    if preflight.status == "block":
        raise OSError("; ".join(messages) or f"Storage preflight blocked move to {target}")

    logger.info(
        "Storage move starting: purpose={} source_class={} target_class={} bytes_est={}",
        purpose,
        source_info.classification,
        target_info.classification,
        estimated_bytes,
    )
    if (
        os.path.isfile(source)
        and _operation_touches_nas(config, source, target)
        and not _same_storage_device(source, target)
    ):
        files = getattr(config, "files", None)
        max_mbps = max(0.0, float(getattr(files, "nas_max_transfer_mbps", 50.0) or 0.0))
        messages.append(
            f"Cross-device NAS copy paced at {max_mbps:g} MiB/s"
            if max_mbps > 0
            else "Cross-device NAS copy uses chunked transfer without a rate limit"
        )
        if not _copy_file_throttled(source, target, config):
            messages.append(
                f"Copy to {target} succeeded but the source file could not be "
                f"removed - a duplicate remains at {source} and needs manual cleanup"
            )
    else:
        shutil.move(source, target)
    logger.info("Storage move completed: purpose={} target={}", purpose, target)
    return StorageOperationResult(
        operation="move",
        purpose=purpose,
        source_path=source,
        target_path=target,
        source_classification=source_info.classification,
        target_classification=target_info.classification,
        status="completed",
        bytes_estimated=estimated_bytes,
        messages=messages,
    )


async def move_path(
    source: str,
    target: str,
    config: Any,
    *,
    purpose: str = "move",
    required_bytes: int | None = None,
) -> StorageOperationResult:
    started_at = _utc_iso()
    started_monotonic = time.monotonic()
    async with _storage_operation_lock([source, target]):
        estimated_bytes = 0
        try:
            estimated_bytes = await asyncio.to_thread(_estimated_path_bytes, source)
            async with _nas_policy_scope(
                operation="move",
                purpose=purpose,
                source_path=source,
                target_path=target,
                config=config,
                estimated_bytes=estimated_bytes,
            ):
                result = await asyncio.to_thread(
                    _move_path_sync,
                    source,
                    target,
                    config,
                    purpose,
                    required_bytes,
                    estimated_bytes,
                )
        except Exception as exc:
            failed = _failed_operation_result(
                operation="move",
                purpose=purpose,
                source_path=source,
                target_path=target,
                config=config,
                started_at=started_at,
                started_monotonic=started_monotonic,
                error=exc,
                bytes_estimated=estimated_bytes,
            )
            _record_operation(failed)
            await _persist_operation(failed)
            raise
        completed = _operation_result_with_timing(
            result,
            started_at=started_at,
            completed_at=_utc_iso(),
            started_monotonic=started_monotonic,
        )
        _record_operation(completed)
        await _persist_operation(completed)
        return completed


def _remove_path_sync(
    path: str,
    config: Any,
    purpose: str,
    recursive: bool,
    estimated_bytes: int,
) -> StorageOperationResult:
    source_info = classify_storage_path(path, config)
    messages: list[str] = []
    if source_info.classification in {"nas", "network"}:
        messages.append("Network/NAS path detected; delete operation should use NAS-safe pacing")

    if not os.path.exists(path):
        messages.append("Path does not exist; remove skipped")
        return StorageOperationResult(
            operation="remove",
            purpose=purpose,
            source_path=path,
            target_path=None,
            source_classification=source_info.classification,
            target_classification=None,
            status="skipped",
            bytes_estimated=0,
            messages=messages,
        )

    logger.info(
        "Storage remove starting: purpose={} source_class={} bytes_est={} recursive={}",
        purpose,
        source_info.classification,
        estimated_bytes,
        recursive,
    )
    if os.path.isdir(path):
        if not recursive:
            raise IsADirectoryError(f"Refusing non-recursive directory delete: {path}")
        shutil.rmtree(path, ignore_errors=False)
    else:
        os.remove(path)
    logger.info("Storage remove completed: purpose={} path={}", purpose, path)
    return StorageOperationResult(
        operation="remove",
        purpose=purpose,
        source_path=path,
        target_path=None,
        source_classification=source_info.classification,
        target_classification=None,
        status="completed",
        bytes_estimated=estimated_bytes,
        messages=messages,
    )


async def remove_path(
    path: str,
    config: Any,
    *,
    purpose: str = "remove",
    recursive: bool = False,
    estimated_bytes: int | None = None,
) -> StorageOperationResult:
    started_at = _utc_iso()
    started_monotonic = time.monotonic()
    async with _storage_operation_lock([path]):
        measured_bytes = max(0, int(estimated_bytes or 0))
        try:
            if estimated_bytes is None:
                measured_bytes = await asyncio.to_thread(_estimated_path_bytes, path)
            async with _nas_policy_scope(
                operation="remove",
                purpose=purpose,
                source_path=path,
                target_path=None,
                config=config,
                estimated_bytes=measured_bytes,
            ):
                result = await asyncio.to_thread(
                    _remove_path_sync,
                    path,
                    config,
                    purpose,
                    recursive,
                    measured_bytes,
                )
        except Exception as exc:
            failed = _failed_operation_result(
                operation="remove",
                purpose=purpose,
                source_path=path,
                target_path=None,
                config=config,
                started_at=started_at,
                started_monotonic=started_monotonic,
                error=exc,
                bytes_estimated=measured_bytes,
            )
            _record_operation(failed)
            await _persist_operation(failed)
            raise
        completed = _operation_result_with_timing(
            result,
            started_at=started_at,
            completed_at=_utc_iso(),
            started_monotonic=started_monotonic,
        )
        _record_operation(completed)
        await _persist_operation(completed)
        return completed
