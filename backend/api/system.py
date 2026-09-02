"""System/health API routes."""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import platform
import shutil
import sys
import time
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from starlette.background import BackgroundTask

from backend.api.models import (
    ActionStatusResponse,
    DecisionAuditItem,
    DuplicateCleanupPreviewResponse,
    HealthMatrixResponse,
    IntegrationMatrixResponse,
    NasPressureResponse,
    PreflightResponse,
    RecyclingBinEmptyResponse,
    RecyclingBinInfoResponse,
    ReplacementRecoveryResponse,
    SearchDiagnosticsResponse,
    SearchDiagnosticsHistoryResponse,
    SearchTestRequest,
    SearchTestResponse,
    StorageOperationsResponse,
    StoragePreflightResponse,
    SystemHealthResponse,
    SystemInfoResponse,
    SystemStatusResponse,
    TelemetryPurgeResponse,
    UtilitiesMaintenanceInsightsResponse,
    UpdateCheckResponse,
)
from backend.auth.dependencies import get_current_user
from backend.core.orchestrator import get_status, is_running, request_stop
from backend.database import ActivityLog, DecisionAuditLog, Download, Movie, ReplacementRecoveryRecord, async_session
from backend.scheduler.scheduler import get_scheduler, list_jobs
from backend.utils.responses import not_found, get_correlation_id
from backend.version import APP_VERSION

router = APIRouter(prefix="/system", tags=["system"])

_active_manual_tasks: set[str] = set()
_active_manual_tasks_lock = asyncio.Lock()


async def _start_guarded_background_task(task_key: str, background: BackgroundTasks, task_func) -> bool:
    """Start a background task once per key until completion."""
    async with _active_manual_tasks_lock:
        if task_key in _active_manual_tasks:
            return False
        _active_manual_tasks.add(task_key)

    async def _runner() -> None:
        try:
            result = task_func()
            if inspect.isawaitable(result):
                await result
        finally:
            async with _active_manual_tasks_lock:
                _active_manual_tasks.discard(task_key)

    background.add_task(_runner)
    return True

_start_time = datetime.now(timezone.utc)


CURRENT_VERSION = APP_VERSION
GITHUB_REPO = "theantipopau/slimarr"

_SERVICES_HEALTH_TTL_SECONDS = 20.0
_services_health_cache: dict[str, Any] | None = None
_services_health_cache_at = 0.0
_services_health_lock = asyncio.Lock()

_RECYCLE_STATS_TTL_SECONDS = 60.0
_recycle_stats_cache: dict[str, Any] | None = None
_recycle_stats_cache_at = 0.0
_recycle_stats_lock = asyncio.Lock()

_DUPLICATE_PREVIEW_TTL_SECONDS = 10 * 60.0
_duplicate_preview_cache: dict[str, Any] | None = None
_duplicate_preview_cache_at = 0.0
_duplicate_preview_lock = asyncio.Lock()


def invalidate_services_health_cache() -> None:
    """Clear cached integration health after settings changes."""
    global _services_health_cache, _services_health_cache_at
    _services_health_cache = None
    _services_health_cache_at = 0.0


def _get_recycling_bin_path() -> str:
    from backend.config import get_config
    cfg = get_config()
    return (cfg.files.recycling_bin or "").strip()


def _dir_stats(path: str) -> tuple[int, int]:
    """Return (files_count, total_bytes) for a directory tree."""
    files_count = 0
    total_bytes = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            files_count += 1
            file_path = os.path.join(root, name)
            try:
                total_bytes += os.path.getsize(file_path)
            except OSError:
                # Ignore unreadable files but keep scanning
                pass
    return files_count, total_bytes


def _recycle_entries(path: str) -> list[tuple[str, str, int, int]]:
    """Snapshot recycle entries and sizes in one worker-thread traversal."""
    entries: list[tuple[str, str, int, int]] = []
    with os.scandir(path) as iterator:
        for entry in iterator:
            try:
                if entry.is_file(follow_symlinks=False):
                    try:
                        size = int(entry.stat(follow_symlinks=False).st_size)
                    except OSError:
                        size = 0
                    entries.append((entry.path, "file", 1, size))
                elif entry.is_dir(follow_symlinks=False):
                    files_count, total_bytes = _dir_stats(entry.path)
                    entries.append((entry.path, "directory", files_count, total_bytes))
            except OSError:
                continue
    return entries


def _invalidate_recycle_stats_cache() -> None:
    global _recycle_stats_cache, _recycle_stats_cache_at
    _recycle_stats_cache = None
    _recycle_stats_cache_at = 0.0


def _empty_duplicate_preview(status: str = "not_cached", reason: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "movies_scanned": 0,
        "duplicates_found": 0,
        "estimated_reclaimable_bytes": 0,
        "confidence": {"high": 0, "medium": 0, "low": 0},
        "sample": [],
        "truncated": False,
    }


async def _duplicate_preview_cached(
    *,
    max_movies_per_section: int = 500,
    force: bool = False,
    allow_scan: bool = True,
) -> dict[str, Any]:
    global _duplicate_preview_cache, _duplicate_preview_cache_at

    max_movies_per_section = max(1, int(max_movies_per_section or 500))
    now = time.monotonic()
    cached = _duplicate_preview_cache
    if (
        not force
        and cached
        and int(cached.get("max_movies_per_section") or 0) >= max_movies_per_section
        and (now - _duplicate_preview_cache_at) <= _DUPLICATE_PREVIEW_TTL_SECONDS
    ):
        return dict(cached.get("payload") or _empty_duplicate_preview())

    if not allow_scan:
        if cached and int(cached.get("max_movies_per_section") or 0) >= max_movies_per_section:
            return dict(cached.get("payload") or _empty_duplicate_preview())
        return _empty_duplicate_preview(
            reason="Duplicate preview has not been generated yet. Refresh preview to populate maintenance telemetry."
        )

    async with _duplicate_preview_lock:
        now = time.monotonic()
        cached = _duplicate_preview_cache
        if (
            not force
            and cached
            and int(cached.get("max_movies_per_section") or 0) >= max_movies_per_section
            and (now - _duplicate_preview_cache_at) <= _DUPLICATE_PREVIEW_TTL_SECONDS
        ):
            return dict(cached.get("payload") or _empty_duplicate_preview())

        from backend.core.cleanup import preview_duplicate_cleanup

        payload = await preview_duplicate_cleanup(max_movies_per_section=max_movies_per_section)
        _duplicate_preview_cache = {
            "max_movies_per_section": max_movies_per_section,
            "payload": payload,
        }
        _duplicate_preview_cache_at = time.monotonic()
        return dict(payload)


async def _dir_stats_cached(path: str) -> tuple[int, int]:
    global _recycle_stats_cache, _recycle_stats_cache_at

    now = time.monotonic()
    cached = _recycle_stats_cache
    if (
        cached
        and cached.get("path") == path
        and (now - _recycle_stats_cache_at) <= _RECYCLE_STATS_TTL_SECONDS
    ):
        return int(cached.get("files", 0)), int(cached.get("bytes", 0))

    async with _recycle_stats_lock:
        now = time.monotonic()
        cached = _recycle_stats_cache
        if (
            cached
            and cached.get("path") == path
            and (now - _recycle_stats_cache_at) <= _RECYCLE_STATS_TTL_SECONDS
        ):
            return int(cached.get("files", 0)), int(cached.get("bytes", 0))

        files_count, total_bytes = await asyncio.to_thread(_dir_stats, path)
        _recycle_stats_cache = {
            "path": path,
            "files": files_count,
            "bytes": total_bytes,
        }
        _recycle_stats_cache_at = now
        return files_count, total_bytes


def _check(status: str, name: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "name": name, "message": message}
    if detail is not None:
        result["detail"] = detail
    return result


def _find_existing_parent(path: str) -> str | None:
    current = os.path.abspath(path)
    while current and not os.path.exists(current):
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent
    return current if os.path.exists(current) else None


def _redact_sensitive(data: Any) -> Any:
    """Recursively redact obvious secrets in config-like payloads."""
    secret_markers = ("secret", "token", "password", "api_key", "apikey")
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            key_l = key.lower()
            if any(marker in key_l for marker in secret_markers):
                out[key] = "***"
            else:
                out[key] = _redact_sensitive(value)
        return out
    if isinstance(data, list):
        return [_redact_sensitive(v) for v in data]
    return data


def _redact_path_for_payload(path: str | None) -> str | None:
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


def _decode_json_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _replacement_recovery_payload(record: ReplacementRecoveryRecord, *, redact_paths: bool = True) -> dict[str, Any]:
    payload = {
        "id": record.id,
        "download_id": record.download_id,
        "movie_id": record.movie_id,
        "movie_title": record.movie_title,
        "status": record.status,
        "phase": record.phase,
        "original_path": record.original_path,
        "mapped_path": record.mapped_path,
        "target_path": record.target_path,
        "video_file_path": record.video_file_path,
        "storage_path": record.storage_path,
        "recycle_path": record.recycle_path,
        "fallback_backup_path": record.fallback_backup_path,
        "error_message": record.error_message,
        "details": _decode_json_payload(record.details),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }
    if redact_paths:
        for key in (
            "original_path",
            "mapped_path",
            "target_path",
            "video_file_path",
            "storage_path",
            "recycle_path",
            "fallback_backup_path",
        ):
            payload[key] = _redact_path_for_payload(payload.get(key))
    return payload


def _serializable_search_detail(detail: dict[str, Any]) -> dict[str, Any]:
    from backend.core.search_diagnostics import redact_text, redact_url

    def _clean(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                key_l = str(key).lower()
                if any(marker in key_l for marker in ("api_key", "apikey", "token", "password", "secret")):
                    out[key] = "***"
                elif key_l.endswith("url") or key_l in {"link", "guid"}:
                    out[key] = redact_url(str(item))
                else:
                    out[key] = _clean(item)
            return out
        if isinstance(value, list):
            return [_clean(item) for item in value]
        if isinstance(value, str):
            return redact_text(value)
        return value

    cleaned = _clean(detail)
    cleaned.pop("exception", None)
    if cleaned.get("request_url"):
        cleaned["request_url"] = redact_url(str(cleaned["request_url"]))
    return cleaned


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _json_string_list(value: str | None) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except Exception:
        pass
    return []


def _read_log_tail(path: str, max_lines: int = 2000) -> str:
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return ""


def _cleanup_dir(path: str) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _disk_preflight_check(name: str, path: str, warn_below_gb: float = 10.0, block_below_gb: float = 1.0) -> dict[str, Any]:
    existing_path = _find_existing_parent(path)
    if not existing_path:
        return _check("block", name, f"No accessible parent path for {path}", {"path": path})

    usage = shutil.disk_usage(existing_path)
    free_gb = usage.free / (1024 ** 3)
    detail = {
        "path": existing_path,
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "free_gb": round(free_gb, 2),
    }
    if free_gb < block_below_gb:
        return _check("block", name, f"{free_gb:.2f} GB free at {existing_path}", detail)
    if free_gb < warn_below_gb:
        return _check("warn", name, f"{free_gb:.2f} GB free at {existing_path}", detail)
    return _check("ok", name, f"{free_gb:.2f} GB free at {existing_path}", detail)


@router.get("/health", response_model=SystemHealthResponse)
async def health():
    """Lightweight health probe for Docker/k8s readiness checks.

    Returns HTTP 200 if the API is accepting traffic.
    Does NOT check external services — use /health/matrix for that.
    """
    from backend.core.startup import get_startup_warnings
    warnings = get_startup_warnings()
    return {
        "status": "ok" if not warnings else "degraded",
        **({"warnings": warnings} if warnings else {}),
    }


@router.get("/metrics")
async def metrics():
    """Prometheus-compatible plain-text metrics endpoint.

    No authentication required so Prometheus can scrape without credentials.
    Exposes basic counters/gauges for operational observability.
    """
    from backend.config import get_config
    from backend.utils.platform import disk_free_bytes, is_docker

    lines: list[str] = []

    def _gauge(name: str, value: float | int, labels: dict[str, str] | None = None, help_text: str = "") -> None:
        if help_text:
            lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        label_str = ""
        if labels:
            label_str = "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
        lines.append(f"{name}{label_str} {value}")

    def _counter(name: str, value: float | int, labels: dict[str, str] | None = None, help_text: str = "") -> None:
        if help_text:
            lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        label_str = ""
        if labels:
            label_str = "{" + ",".join(f'{k}="{v}"' for k, v in labels.items()) + "}"
        lines.append(f"{name}{label_str} {value}")

    uptime_seconds = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    _gauge("slimarr_uptime_seconds", uptime_seconds, help_text="Seconds since process start")

    cfg = get_config()
    _gauge("slimarr_info", 1, labels={"version": CURRENT_VERSION, "in_docker": str(is_docker()).lower()}, help_text="Slimarr build info")

    try:
        from backend.database import JobRecord

        async with async_session() as db:
            movies_total = (await db.execute(select(func.count()).select_from(Movie))).scalar_one()
            active_downloads = (
                await db.execute(
                    select(func.count()).select_from(Download).where(
                        Download.status.in_(["queued", "downloading", "processing"])
                    )
                )
            ).scalar_one()
            active_jobs = (
                await db.execute(
                    select(func.count()).select_from(JobRecord).where(
                        JobRecord.status.in_(["queued", "running", "cancelling"])
                    )
                )
            ).scalar_one()
            failed_jobs = (
                await db.execute(
                    select(func.count()).select_from(JobRecord).where(JobRecord.status == "failed")
                )
            ).scalar_one()
        _gauge("slimarr_movies_total", int(movies_total), help_text="Total movies in the library")
        _gauge("slimarr_downloads_active", int(active_downloads), help_text="Active downloads in queue")
        _gauge("slimarr_jobs_active", int(active_jobs), help_text="Active persistent jobs")
        _counter("slimarr_jobs_failed_total", int(failed_jobs), help_text="Failed persistent jobs")
    except Exception:
        pass

    db_path = os.environ.get("SLIMARR_DB") or "data/slimarr.db"
    if os.path.exists(db_path):
        _gauge("slimarr_db_size_bytes", os.path.getsize(db_path), help_text="SQLite database file size in bytes")

    free = disk_free_bytes("data")
    if free is not None:
        _gauge("slimarr_disk_free_bytes", free, help_text="Free bytes on the data partition")

    cycle = get_status()
    _gauge("slimarr_cycle_running", 1 if cycle.get("running") else 0, help_text="1 if an automation cycle is running")

    from backend.core.search_diagnostics import degradation_status
    degraded = degradation_status()
    _gauge("slimarr_search_degraded", 1 if degraded.get("degraded") else 0, help_text="1 if search pipeline is degraded")

    from backend.core.storage import nas_policy_snapshot, storage_operation_metrics
    storage_metrics = storage_operation_metrics()
    emitted_storage_operations_help = False
    emitted_storage_bytes_help = False
    for operation in ("move", "remove"):
        for status_name in ("completed", "failed", "skipped"):
            value = storage_metrics.get(f"{operation}:{status_name}", 0)
            _counter(
                "slimarr_storage_operations_total",
                value,
                labels={"operation": operation, "status": status_name},
                help_text=(
                    "Storage operations by operation and status"
                    if not emitted_storage_operations_help
                    else ""
                ),
            )
            emitted_storage_operations_help = True
        _counter(
            "slimarr_storage_operation_bytes_total",
            storage_metrics.get(f"{operation}:bytes_estimated", 0),
            labels={"operation": operation},
            help_text=(
                "Estimated bytes processed by completed storage operations"
                if not emitted_storage_bytes_help
                else ""
            ),
        )
        emitted_storage_bytes_help = True
    _counter(
        "slimarr_storage_operation_failures_total",
        storage_metrics.get("move:failed", 0) + storage_metrics.get("remove:failed", 0),
        help_text="Total failed storage operations",
    )
    nas_policy = nas_policy_snapshot(redact_paths=True)
    _gauge(
        "slimarr_nas_cooldown_active",
        1 if nas_policy.get("cooldown_active") else 0,
        help_text="1 if NAS storage operations are in failure cooldown",
    )
    _gauge(
        "slimarr_nas_storage_operations_active",
        int(nas_policy.get("active_operations") or 0),
        help_text="Currently active NAS storage operations",
    )

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@router.get("/startup")
async def startup_context(user=Depends(get_current_user)):
    """Return the startup validation context (directories, disk, runtime, config summary)."""
    from backend.core.startup import get_startup_context, get_startup_warnings
    return {
        "context": get_startup_context(),
        "warnings": get_startup_warnings(),
    }


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info(user=Depends(get_current_user)):
    """Return version, uptime, DB size, and platform info."""
    from backend.config import get_config
    from backend.utils.platform import is_docker, container_id
    from backend.database import database_runtime_info
    cfg = get_config()
    db_path = os.environ.get("SLIMARR_DB") or "data/slimarr.db"
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    uptime_seconds = int((datetime.now(timezone.utc) - _start_time).total_seconds())
    db_runtime = database_runtime_info()
    pool = db_runtime.get("pool") if isinstance(db_runtime, dict) else {}
    if not isinstance(pool, dict):
        pool = {}

    return {
        "version": CURRENT_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "arch": platform.machine(),
        "db_backend": db_runtime.get("backend") if isinstance(db_runtime, dict) else None,
        "db_schema_version": db_runtime.get("schema_version") if isinstance(db_runtime, dict) else None,
        "db_pool_checked_out": pool.get("checked_out"),
        "in_docker": is_docker(),
        "container_id": container_id() or "",
        "uptime_seconds": uptime_seconds,
        "db_size_bytes": db_size,
        "port": cfg.server.port,
    }


@router.get("/diagnostics/bundle")
async def diagnostics_bundle(user=Depends(get_current_user)):
    """Build and download a support diagnostics zip with redacted config and health snapshots."""
    from backend.config import get_config

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    temp_dir = tempfile.mkdtemp(prefix="slimarr-diagnostics-")
    payload_dir = os.path.join(temp_dir, "payload")
    os.makedirs(payload_dir, exist_ok=True)

    config_dump = _redact_sensitive(get_config().model_dump())
    services = await _build_services_health()
    matrix = await integration_matrix(user)
    health = await health_matrix(user)
    info = await get_system_info(user)
    search_diag = await search_diagnostics(user)
    from backend.core.storage import persisted_storage_operation_snapshot, storage_operation_snapshot
    from backend.core.jobs import get_persistent_job, list_persistent_jobs
    storage_operations = storage_operation_snapshot(redact_paths=True, limit=200)
    storage_operations["persisted"] = await persisted_storage_operation_snapshot(
        redact_paths=True,
        limit=500,
    )
    job_rows = await list_persistent_jobs(status="all", limit=200)
    job_timeline = []
    for item in job_rows.get("jobs", []):
        job_id = item.get("id")
        if job_id:
            detail = await get_persistent_job(str(job_id))
            if detail:
                job_timeline.append(detail)
    async with async_session() as db:
        recovery_rows = (
            await db.execute(
                select(ReplacementRecoveryRecord)
                .order_by(
                    ReplacementRecoveryRecord.updated_at.desc(),
                    ReplacementRecoveryRecord.id.desc(),
                )
                .limit(200)
            )
        ).scalars().all()
    replacement_recovery = [
        _replacement_recovery_payload(row, redact_paths=True)
        for row in recovery_rows
    ]

    with open(os.path.join(payload_dir, "config.redacted.json"), "w", encoding="utf-8") as f:
        json.dump(config_dump, f, indent=2)
    with open(os.path.join(payload_dir, "system.info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2)
    with open(os.path.join(payload_dir, "system.health.matrix.json"), "w", encoding="utf-8") as f:
        json.dump(health, f, indent=2)
    with open(os.path.join(payload_dir, "system.integrations.matrix.json"), "w", encoding="utf-8") as f:
        json.dump(matrix, f, indent=2)
    with open(os.path.join(payload_dir, "system.services.health.json"), "w", encoding="utf-8") as f:
        json.dump(services, f, indent=2)
    with open(os.path.join(payload_dir, "system.search.diagnostics.json"), "w", encoding="utf-8") as f:
        json.dump(search_diag, f, indent=2)
    from backend.core.search_diagnostics import history as search_history
    with open(os.path.join(payload_dir, "system.search.diagnostics.history.json"), "w", encoding="utf-8") as f:
        json.dump(search_history(page=1, per_page=500), f, indent=2)
    with open(os.path.join(payload_dir, "system.storage.operations.json"), "w", encoding="utf-8") as f:
        json.dump(storage_operations, f, indent=2)
    with open(os.path.join(payload_dir, "system.jobs.timeline.json"), "w", encoding="utf-8") as f:
        json.dump(job_timeline, f, indent=2)
    with open(os.path.join(payload_dir, "system.replacement.recovery.json"), "w", encoding="utf-8") as f:
        json.dump(replacement_recovery, f, indent=2)

    # NAS path classification summary
    try:
        from backend.core.storage import classify_storage_path, nas_policy_snapshot
        cfg_for_bundle = get_config()
        nas_prefixes = list(cfg_for_bundle.files.nas_path_prefixes or [])
        nas_summary: dict[str, Any] = {
            "nas_path_prefixes": nas_prefixes,
            "nas_policy": nas_policy_snapshot(redact_paths=True),
            "path_classifications": {
                _redact_path_for_payload(p): classify_storage_path(p, cfg_for_bundle).classification
                for p in nas_prefixes
            },
        }
        with open(os.path.join(payload_dir, "system.nas.classification.json"), "w", encoding="utf-8") as f:
            json.dump(nas_summary, f, indent=2)
    except Exception:
        pass

    log_tail = _read_log_tail(os.path.join("data", "logs", "slimarr.log"), max_lines=3000)
    with open(os.path.join(payload_dir, "logs.slimarr.tail.log"), "w", encoding="utf-8") as f:
        f.write(log_tail)

    bundle_name = f"slimarr-diagnostics-{ts}.zip"
    bundle_path = os.path.join(temp_dir, bundle_name)
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(payload_dir):
            for name in files:
                abs_path = os.path.join(root, name)
                rel_path = os.path.relpath(abs_path, payload_dir)
                zf.write(abs_path, arcname=rel_path)

    return FileResponse(
        bundle_path,
        media_type="application/zip",
        filename=bundle_name,
        background=BackgroundTask(_cleanup_dir, temp_dir),
    )


@router.get("/update-check", response_model=UpdateCheckResponse)
async def check_for_update(user=Depends(get_current_user)):
    """Check GitHub releases for a newer version."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            )
            if resp.status_code == 404:
                # No releases published yet
                return {"update_available": False, "current": CURRENT_VERSION, "latest": CURRENT_VERSION}
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"update_available": False, "current": CURRENT_VERSION, "error": str(e)}

    latest_tag = data.get("tag_name", "").lstrip("v")
    latest_name = data.get("name", latest_tag)
    release_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases/latest")
    published_at = data.get("published_at", "")

    def _version_tuple(v: str):
        try:
            return tuple(int(x) for x in v.split("."))
        except Exception:
            return (0,)

    update_available = _version_tuple(latest_tag) > _version_tuple(CURRENT_VERSION)
    return {
        "update_available": update_available,
        "current": CURRENT_VERSION,
        "latest": latest_tag,
        "latest_name": latest_name,
        "release_url": release_url,
        "published_at": published_at,
    }


@router.get("/recycling-bin", response_model=RecyclingBinInfoResponse)
async def recycling_bin_info(user=Depends(get_current_user)):
    """Return live recycling bin status and size."""
    recycle_path = _get_recycling_bin_path()
    if not recycle_path:
        return {
            "enabled": False,
            "path": "",
            "exists": False,
            "files": 0,
            "bytes": 0,
        }

    exists = await asyncio.to_thread(os.path.isdir, recycle_path)
    files_count, total_bytes = await _dir_stats_cached(recycle_path) if exists else (0, 0)
    return {
        "enabled": True,
        "path": recycle_path,
        "exists": exists,
        "files": files_count,
        "bytes": total_bytes,
    }


@router.post("/recycling-bin/empty", response_model=RecyclingBinEmptyResponse)
async def recycling_bin_empty(user=Depends(get_current_user)):
    """Delete all files/folders inside the configured recycling bin."""
    from backend.config import get_config
    from backend.core.storage import remove_path

    recycle_path = _get_recycling_bin_path()
    if not recycle_path:
        return {"status": "disabled", "removed_files": 0, "removed_dirs": 0, "freed_bytes": 0}

    if not await asyncio.to_thread(os.path.isdir, recycle_path):
        return {"status": "not_found", "removed_files": 0, "removed_dirs": 0, "freed_bytes": 0}

    removed_files = 0
    removed_dirs = 0
    freed_bytes = 0

    entries = await asyncio.to_thread(_recycle_entries, recycle_path)
    for entry_path, entry_kind, files_count, bytes_count in entries:
        try:
            if entry_kind == "file":
                await remove_path(
                    entry_path,
                    get_config(),
                    purpose="empty_recycling_bin",
                    estimated_bytes=bytes_count,
                )
                removed_files += 1
                freed_bytes += bytes_count
            elif entry_kind == "directory":
                await remove_path(
                    entry_path,
                    get_config(),
                    purpose="empty_recycling_bin",
                    recursive=True,
                    estimated_bytes=bytes_count,
                )
                removed_dirs += 1
                removed_files += files_count
                freed_bytes += bytes_count
        except Exception:
            # Continue cleaning even if one entry fails
            continue

    _invalidate_recycle_stats_cache()

    return {
        "status": "emptied",
        "removed_files": removed_files,
        "removed_dirs": removed_dirs,
        "freed_bytes": freed_bytes,
    }


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(user=Depends(get_current_user)):
    scheduler = get_scheduler()
    return {
        "cycle": get_status(),
        "scheduler_running": scheduler.running if scheduler else False,
        "jobs": list_jobs(),
    }


@router.get("/search-diagnostics", response_model=SearchDiagnosticsResponse)
async def search_diagnostics(user=Depends(get_current_user)):
    """Return live search pipeline diagnostics and degradation state."""
    from backend.core.search_diagnostics import snapshot

    return snapshot()


@router.get("/search-diagnostics/history", response_model=SearchDiagnosticsHistoryResponse)
async def search_diagnostics_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    event_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    user=Depends(get_current_user),
):
    """Return persisted diagnostics history with basic search and pagination."""
    from backend.core.search_diagnostics import history

    return history(page=page, per_page=per_page, event_type=event_type, query=q)


@router.post("/search-diagnostics/test", response_model=SearchTestResponse)
async def search_test_harness(payload: SearchTestRequest, user=Depends(get_current_user)):
    """Run a manual movie search and expose raw, parsed, and filtered stages."""
    from backend.config import get_config
    from backend.core.comparer import compare_release
    from backend.core.parser import parse_release_title
    from backend.integrations.newznab import NewznabClient
    from backend.integrations.prowlarr import ProwlarrClient

    cfg = get_config()
    query = f"{payload.title} {payload.year}" if payload.year else payload.title
    providers: list[dict[str, Any]] = []

    if cfg.prowlarr.enabled and cfg.prowlarr.url:
        prowlarr = ProwlarrClient()
        detail = await prowlarr.search_detailed(
            query=query,
            imdb_id=payload.imdb_id or "",
            include_raw=payload.include_raw,
        )
        providers.append(_serializable_search_detail(detail))

    for idx in [item for item in cfg.indexers if item.name and item.url]:
        client = NewznabClient(idx)
        if payload.imdb_id:
            clean_id = payload.imdb_id.lstrip("tt")
            params = {
                "t": "movie",
                "imdbid": clean_id,
                "apikey": idx.api_key,
                "cat": ",".join(str(cat) for cat in idx.categories),
                "limit": 100,
            }
        else:
            params = {
                "t": "search",
                "q": query,
                "apikey": idx.api_key,
                "cat": ",".join(str(cat) for cat in idx.categories),
                "limit": 100,
            }
        detail = await client.search_detailed(params, include_raw=payload.include_raw)
        providers.append(_serializable_search_detail(detail))

    parsed_results: list[dict[str, Any]] = []
    for provider in providers:
        parsed_results.extend(provider.get("parsed_results", []))

    filtering_stages = [
        {"stage": "provider_raw", "count": sum(int(p.get("raw_count") or 0) for p in providers)},
        {"stage": "provider_parsed", "count": len(parsed_results)},
    ]

    seen_urls: set[str] = set()
    unique_results: list[dict[str, Any]] = []
    duplicate_count = 0
    for result in parsed_results:
        url = result.get("nzb_url", "")
        if url and url in seen_urls:
            duplicate_count += 1
            continue
        if url:
            seen_urls.add(url)
        unique_results.append(result)

    filtering_stages.append({"stage": "deduplicated", "count": len(unique_results), "removed": duplicate_count})

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    local_size = 10 * 1024 * 1024 * 1024
    for result in unique_results:
        parsed = parse_release_title(result.get("release_title", ""))
        cmp = compare_release(
            local_size=local_size,
            local_resolution="1080p",
            local_codec="h264",
            candidate_size=int(result.get("size") or 0),
            candidate_title=result.get("release_title", ""),
            movie_title=payload.title,
            movie_year=payload.year,
        )
        item = {
            **result,
            "resolution": parsed.resolution,
            "video_codec": parsed.video_codec,
            "audio_codec": parsed.audio_codec,
            "audio_channels": parsed.audio_channels,
            "source": parsed.source,
            "hdr": parsed.hdr,
            "languages": parsed.languages,
            "subtitle_markers": parsed.subtitle_markers,
            "media_health_score": cmp.media_health_score,
            "media_health_rating": cmp.media_health_rating,
            "media_health_reasons": cmp.media_health_reasons or [],
            "decision": cmp.decision,
            "score": cmp.score,
            "confidence_score": cmp.confidence_score,
            "confidence_breakdown": cmp.confidence_breakdown,
            "reject_reason": cmp.reject_reason,
            "savings_pct": cmp.savings_pct,
        }
        if cmp.decision == "accept":
            accepted.append(item)
        else:
            rejected.append(item)

    filtering_stages.append({"stage": "accepted", "count": len(accepted)})
    filtering_stages.append({"stage": "rejected", "count": len(rejected)})

    return {
        "query": {
            "title": payload.title,
            "year": payload.year,
            "imdb_id": payload.imdb_id,
            "query": query,
            "comparison_baseline": "10 GiB 1080p h264 local file",
        },
        "providers": providers,
        "raw_total": sum(int(p.get("raw_count") or 0) for p in providers),
        "parsed_total": len(parsed_results),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted_results": accepted[:100],
        "rejected_results": rejected[:100],
        "filtering_stages": filtering_stages,
    }


@router.get("/tasks")
async def list_tasks(user=Depends(get_current_user)):
    return list_jobs()


@router.post("/tasks/{task_id}/run", response_model=ActionStatusResponse)
async def run_task(task_id: str, user=Depends(get_current_user)):
    scheduler = get_scheduler()
    job = scheduler.get_job(task_id)
    if not job:
        raise not_found(f"Task '{task_id}'", correlation_id=get_correlation_id())
    from backend.core.jobs import enqueue_job

    result = await enqueue_job(
        "scheduler_task",
        {"task_id": task_id},
        singleton=False,
    )
    return {
        "status": "triggered",
        "task_id": task_id,
        "job_id": result["job"]["id"],
    }


@router.post("/scan", response_model=ActionStatusResponse)
async def trigger_scan(user=Depends(get_current_user)):
    """Trigger a full library scan in the background."""
    from backend.core.scanner import is_scan_running
    from backend.core.orchestrator import is_running as is_cycle_running
    if is_scan_running() or is_cycle_running():
        return {"status": "already_running"}
    from backend.core.jobs import enqueue_job

    result = await enqueue_job("manual_scan")
    if result["already_running"]:
        return {"status": "already_running"}
    return {"status": "scan_started", "job_id": result["job"]["id"]}


@router.post("/cleanup", response_model=ActionStatusResponse)
async def trigger_cleanup(
    confirm: bool = Query(default=False),
    user=Depends(get_current_user),
):
    """Trigger a duplicate file cleanup in the library."""
    if not confirm:
        return {"status": "confirmation_required"}

    from backend.core.jobs import enqueue_job

    result = await enqueue_job("duplicate_cleanup")
    if result["already_running"]:
        return {"status": "already_running"}
    return {"status": "cleanup_started", "job_id": result["job"]["id"]}


@router.get("/cleanup/preview", response_model=DuplicateCleanupPreviewResponse)
async def cleanup_preview(
    force: bool = Query(default=False),
    user=Depends(get_current_user),
):
    """Preview duplicate cleanup impact without deleting any file."""
    if force:
        from backend.core.jobs import enqueue_job

        result = await enqueue_job(
            "duplicate_preview",
            {"force": True},
            singleton=True,
        )
        cached = await _duplicate_preview_cached(allow_scan=False)
        cached["job_id"] = result["job"]["id"]
        if cached.get("status") == "not_cached":
            cached["status"] = "queued"
            cached["reason"] = "Duplicate preview job queued"
        return cached
    return await _duplicate_preview_cached(force=force)


@router.get("/utilities/maintenance-insights", response_model=UtilitiesMaintenanceInsightsResponse)
async def utilities_maintenance_insights(user=Depends(get_current_user)):
    """Return telemetry-aware utility maintenance score and safe recommendations."""
    from backend.core.search_diagnostics import degradation_status

    health = await health_matrix(user)
    recycle = await recycling_bin_info(user)
    duplicate_preview = await _duplicate_preview_cached(max_movies_per_section=250, allow_scan=False)
    search_state = degradation_status()

    score = 100.0
    signals: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []

    health_status = str(health.get("status") or "unknown")
    if health_status == "down":
        score -= 35.0
    elif health_status == "degraded":
        score -= 15.0
    signals.append(
        {
            "key": "system_health",
            "state": health_status,
            "impact": -35 if health_status == "down" else (-15 if health_status == "degraded" else 0),
            "detail": "Derived from API, DB, scheduler, queue, integrations, and search pipeline health.",
        }
    )

    if search_state.get("degraded"):
        score -= 8.0
        signals.append(
            {
                "key": "search_pipeline",
                "state": "degraded",
                "impact": -8,
                "detail": "; ".join(search_state.get("reasons") or ["Search degradation detected"]),
            }
        )
        recommendations.append(
            {
                "priority": "high",
                "category": "Reliability",
                "title": "Resolve search degradation before heavy maintenance",
                "detail": "Utility actions are safest and most effective when indexer/search telemetry is healthy.",
            }
        )

    reclaimable = int(duplicate_preview.get("estimated_reclaimable_bytes") or 0)
    duplicates_found = int(duplicate_preview.get("duplicates_found") or 0)
    duplicate_status = str(duplicate_preview.get("status") or "unknown")
    if duplicate_status != "ok":
        signals.append(
            {
                "key": "duplicate_media",
                "state": duplicate_status,
                "impact": 0,
                "detail": str(
                    duplicate_preview.get("reason")
                    or "Duplicate preview has not been generated yet."
                ),
            }
        )
        recommendations.append(
            {
                "priority": "low",
                "category": "Storage",
                "title": "Refresh duplicate preview when needed",
                "detail": "Duplicate preview is now manual/cached to avoid repeated Plex and NAS scans.",
            }
        )
    elif duplicates_found > 0:
        duplicate_penalty = min(18.0, float(duplicates_found) / 3.0)
        score -= duplicate_penalty
        signals.append(
            {
                "key": "duplicate_media",
                "state": "actionable",
                "impact": -round(duplicate_penalty, 1),
                "detail": f"{duplicates_found} duplicate titles; estimated reclaimable {reclaimable} bytes.",
            }
        )
        recommendations.append(
            {
                "priority": "medium",
                "category": "Storage",
                "title": "Review duplicate cleanup preview",
                "detail": "Run cleanup only after checking confidence and sample entries in preview mode.",
            }
        )
    else:
        signals.append(
            {
                "key": "duplicate_media",
                "state": "clean",
                "impact": 0,
                "detail": "No duplicate media candidates detected in sampled scan.",
            }
        )

    recycling_enabled = bool(recycle.get("enabled"))
    recycling_files = int(recycle.get("files") or 0)
    recycling_bytes = int(recycle.get("bytes") or 0)
    if recycling_enabled and recycling_files > 0:
        recycle_penalty = min(12.0, recycling_bytes / float(8 * 1024 * 1024 * 1024))
        score -= recycle_penalty
        signals.append(
            {
                "key": "recycling_backlog",
                "state": "pending",
                "impact": -round(recycle_penalty, 1),
                "detail": f"{recycling_files} files waiting in recycling folder.",
            }
        )
        recommendations.append(
            {
                "priority": "low",
                "category": "Storage",
                "title": "Review recycling folder retention",
                "detail": "Purge only when rollback copies are no longer needed.",
            }
        )
    else:
        signals.append(
            {
                "key": "recycling_backlog",
                "state": "clear",
                "impact": 0,
                "detail": "No recycle backlog detected.",
            }
        )

    score = max(0.0, min(100.0, round(score, 1)))
    if score >= 85:
        state = "excellent"
    elif score >= 70:
        state = "good"
    elif score >= 50:
        state = "attention"
    else:
        state = "critical"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "maintenance_score": score,
        "maintenance_state": state,
        "signals": signals,
        "recommendations": recommendations,
        "telemetry": {
            "health_status": health_status,
            "search_degraded": bool(search_state.get("degraded")),
            "duplicates_found": duplicates_found,
            "estimated_reclaimable_bytes": reclaimable,
            "recycling_files": recycling_files,
            "recycling_bytes": recycling_bytes,
            "sample_truncated": bool(duplicate_preview.get("truncated")),
        },
    }


@router.post("/cycle/start", response_model=ActionStatusResponse)
async def start_cycle(user=Depends(get_current_user)):
    if is_running():
        return {"status": "already_running"}
    from backend.core.jobs import enqueue_job

    result = await enqueue_job("full_cycle")
    if result["already_running"]:
        return {"status": "already_running"}
    return {"status": "started", "job_id": result["job"]["id"]}


@router.post("/cycle/stop", response_model=ActionStatusResponse)
async def stop_cycle(user=Depends(get_current_user)):
    if not is_running():
        return {"status": "not_running"}
    request_stop()
    return {"status": "stop_requested"}


@router.get("/preflight", response_model=PreflightResponse)
async def automation_preflight(user=Depends(get_current_user)):
    """Run quick checks before starting a full automation cycle."""
    from backend.config import get_config
    from backend.integrations.download_client import (
        get_active_download_client_name,
        get_download_client_capabilities,
    )

    config = get_config()
    checks: list[dict[str, Any]] = []

    cycle = get_status()
    if cycle.get("running"):
        checks.append(_check("block", "Automation cycle", "A cycle is already running"))
    elif cycle.get("stop_requested"):
        checks.append(_check("warn", "Automation cycle", "A stop request is still pending"))
    else:
        checks.append(_check("ok", "Automation cycle", "No active cycle"))

    try:
        async with async_session() as db:
            active_downloads = (
                await db.execute(
                    select(func.count()).select_from(Download).where(
                        Download.status.in_(["queued", "downloading", "processing"])
                    )
                )
            ).scalar_one()
            failed_pending = (
                await db.execute(
                    select(func.count()).select_from(Download).where(
                        Download.status == "failed",
                        Download.cleanup_status.in_(["pending", "error"]),
                    )
                )
            ).scalar_one()

        active_downloads = int(active_downloads)
        failed_pending = int(failed_pending)
        max_downloads = max(1, int(config.schedule.max_downloads_per_night or 1))
        if active_downloads >= max_downloads:
            checks.append(_check(
                "warn",
                "Queue saturation",
                f"{active_downloads} active downloads already queued or running",
                {"active_downloads": active_downloads, "max_downloads_per_night": max_downloads},
            ))
        else:
            checks.append(_check(
                "ok",
                "Queue saturation",
                f"{active_downloads} active downloads",
                {"active_downloads": active_downloads, "max_downloads_per_night": max_downloads},
            ))

        if failed_pending > 0:
            checks.append(_check(
                "warn",
                "Failed download cleanup",
                f"{failed_pending} failed downloads still need cleanup review",
                {"failed_pending": failed_pending},
            ))
        else:
            checks.append(_check("ok", "Failed download cleanup", "No pending failed cleanup items"))
    except Exception as e:
        checks.append(_check("block", "Database", f"Unable to inspect queue state: {e}"))

    services = await _build_services_health()
    active_client = get_active_download_client_name()
    try:
        capabilities = get_download_client_capabilities(active_client)
        missing_capabilities = [
            label for key, label in [
                ("submit_url", "submit URLs"),
                ("queue_status", "read queue status"),
                ("history_status", "read history status"),
                ("purge", "purge failed jobs"),
                ("storage_path_lookup", "locate storage paths"),
            ]
            if not getattr(capabilities, key)
        ]
        if missing_capabilities:
            checks.append(_check(
                "block",
                "Downloader capabilities",
                f"{active_client} cannot {', '.join(missing_capabilities)}",
                capabilities.to_dict(),
            ))
        else:
            checks.append(_check(
                "ok",
                "Downloader capabilities",
                f"{active_client} supports required automation operations",
                capabilities.to_dict(),
            ))
    except ValueError as e:
        checks.append(_check("block", "Downloader capabilities", str(e)))

    required_services = [
        ("plex", "Plex"),
        (active_client, active_client.upper() if active_client == "nzbget" else active_client.title()),
        ("tmdb", "TMDB"),
    ]
    for key, label in required_services:
        health = services.get(key, {})
        if isinstance(health, dict) and health.get("success"):
            checks.append(_check("ok", label, "Connected"))
        else:
            error = health.get("error", "Unavailable") if isinstance(health, dict) else "Unavailable"
            checks.append(_check("block", label, error))

    prowlarr = services.get("prowlarr", {})
    indexers = services.get("indexers", [])
    has_prowlarr = isinstance(prowlarr, dict) and bool(prowlarr.get("success"))
    healthy_indexers = [
        idx for idx in indexers
        if isinstance(idx, dict) and idx.get("success")
    ] if isinstance(indexers, list) else []
    if has_prowlarr or healthy_indexers:
        source = "Prowlarr" if has_prowlarr else f"{len(healthy_indexers)} direct indexer(s)"
        checks.append(_check("ok", "Search source", f"{source} available"))
    else:
        checks.append(_check("block", "Search source", "No healthy Prowlarr or direct Newznab indexer"))

    if config.radarr.enabled:
        radarr = services.get("radarr", {})
        checks.append(_check(
            "ok" if isinstance(radarr, dict) and radarr.get("success") else "warn",
            "Radarr",
            "Connected" if isinstance(radarr, dict) and radarr.get("success") else str(radarr.get("error", "Unavailable")),
        ))
    if config.sonarr.enabled:
        sonarr = services.get("sonarr", {})
        checks.append(_check(
            "ok" if isinstance(sonarr, dict) and sonarr.get("success") else "warn",
            "Sonarr",
            "Connected" if isinstance(sonarr, dict) and sonarr.get("success") else str(sonarr.get("error", "Unavailable")),
        ))

    checks.append(_disk_preflight_check("Data disk", "data"))
    recycle_path = _get_recycling_bin_path()
    if recycle_path:
        checks.append(_disk_preflight_check("Recycling disk", recycle_path))

    if any(item["status"] == "block" for item in checks):
        overall = "block"
    elif any(item["status"] == "warn" for item in checks):
        overall = "warn"
    else:
        overall = "ok"

    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/storage/preflight", response_model=StoragePreflightResponse)
async def storage_preflight(
    path: str = Query(..., min_length=1),
    required_bytes: int = Query(default=0, ge=0),
    purpose: str = Query(default="storage_path"),
    user=Depends(get_current_user),
):
    """Run a non-mutating storage/path preflight for future file operations."""
    from backend.config import get_config
    from backend.core.storage import preflight_storage_path

    result = await asyncio.to_thread(
        preflight_storage_path,
        path,
        get_config(),
        required_bytes=required_bytes,
        purpose=purpose,
    )
    return result.to_dict()


@router.get("/storage/operations", response_model=StorageOperationsResponse)
async def storage_operations(
    limit: int = Query(default=25, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Return recent storage operation telemetry and NAS policy state."""
    from backend.core.storage import (
        persisted_storage_operation_snapshot,
        refresh_nas_policy_usage,
        storage_operation_snapshot,
    )

    await refresh_nas_policy_usage()
    snapshot = storage_operation_snapshot(redact_paths=True, limit=limit)
    snapshot["persisted"] = await persisted_storage_operation_snapshot(
        redact_paths=True,
        limit=limit,
    )
    return snapshot


@router.post("/telemetry/purge", response_model=TelemetryPurgeResponse)
async def purge_telemetry(
    keep_days: int = Query(default=30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """Manually trigger retention cleanup for old job records and storage operation logs.

    Removes terminal job records (and their events) and storage operation log entries
    that are older than ``keep_days`` days. Active or queued jobs are never removed.
    """
    from backend.core.jobs import purge_old_jobs
    from backend.core.storage import purge_old_storage_operations

    jobs_removed = await purge_old_jobs(keep_days=keep_days)
    ops_removed = await purge_old_storage_operations(keep_days=keep_days)
    return {
        "status": "ok",
        "keep_days": keep_days,
        "jobs_removed": jobs_removed,
        "storage_operations_removed": ops_removed,
    }


@router.get("/replacement-recovery", response_model=ReplacementRecoveryResponse)
async def replacement_recovery(
    status: str = Query(default="active"),
    limit: int = Query(default=25, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Return replacement recovery metadata for interrupted or risky replacements."""
    active_statuses = {"running", "recovery_required"}
    async with async_session() as db:
        query = select(ReplacementRecoveryRecord)
        if status and status != "all":
            if status == "active":
                query = query.where(ReplacementRecoveryRecord.status.in_(active_statuses))
            else:
                query = query.where(ReplacementRecoveryRecord.status == status)
        rows = (
            await db.execute(
                query.order_by(
                    ReplacementRecoveryRecord.updated_at.desc(),
                    ReplacementRecoveryRecord.id.desc(),
                ).limit(limit)
            )
        ).scalars().all()

    records = [_replacement_recovery_payload(row, redact_paths=True) for row in rows]
    if any(row.get("status") == "recovery_required" for row in records):
        overall = "recovery_required"
    elif records:
        overall = "active"
    else:
        overall = "clear"

    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
    }


async def _build_services_health() -> dict[str, Any]:
    """Quick connectivity check for all configured integrations."""
    from backend.config import get_config

    global _services_health_cache, _services_health_cache_at

    now = time.monotonic()
    if (
        _services_health_cache is not None
        and now - _services_health_cache_at < _SERVICES_HEALTH_TTL_SECONDS
    ):
        return _services_health_cache

    async with _services_health_lock:
        now = time.monotonic()
        if (
            _services_health_cache is not None
            and now - _services_health_cache_at < _SERVICES_HEALTH_TTL_SECONDS
        ):
            return _services_health_cache

    config = get_config()

    async def _safe_check(name: str, check) -> tuple[str, Any]:
        try:
            return name, await check()
        except Exception as e:
            return name, {"success": False, "error": str(e)}

    async def _check_plex() -> dict[str, Any]:
        if not (config.plex.url and config.plex.token):
            return {"success": False, "error": "Not configured"}
        from backend.integrations.plex import PlexClient
        return await asyncio.to_thread(PlexClient().test_connection)

    async def _check_sabnzbd() -> dict[str, Any]:
        if not (config.sabnzbd.url and config.sabnzbd.api_key):
            return {"success": False, "error": "Not configured"}
        from backend.integrations.sabnzbd import SABnzbdClient
        return await SABnzbdClient().test_connection()

    async def _check_nzbget() -> dict[str, Any]:
        # Username/password are optional in some installations; URL is the only hard requirement.
        if not config.nzbget.url:
            return {"success": False, "error": "Not configured"}
        from backend.integrations.nzbget import NZBGetClient
        return await NZBGetClient().test_connection()

    async def _check_radarr() -> dict[str, Any]:
        if not config.radarr.enabled:
            return {"success": False, "error": "Disabled"}
        if not (config.radarr.url and config.radarr.api_key):
            return {"success": False, "error": "Missing URL or API key"}
        if not config.radarr.url.startswith(("http://", "https://")):
            return {"success": False, "error": "URL missing http:// or https:// prefix"}
        from backend.integrations.radarr import RadarrClient
        return await RadarrClient().test_connection()

    async def _check_sonarr() -> dict[str, Any]:
        if not config.sonarr.enabled:
            return {"success": False, "error": "Disabled"}
        if not (config.sonarr.url and config.sonarr.api_key):
            return {"success": False, "error": "Missing URL or API key"}
        if not config.sonarr.url.startswith(("http://", "https://")):
            return {"success": False, "error": "URL missing http:// or https:// prefix"}
        from backend.integrations.sonarr import SonarrClient
        return await SonarrClient().test_connection()

    async def _check_prowlarr() -> dict[str, Any]:
        if not config.prowlarr.enabled:
            return {"success": False, "error": "Disabled"}
        if not (config.prowlarr.url and config.prowlarr.api_key):
            return {"success": False, "error": "Missing URL or API key"}
        if not config.prowlarr.url.startswith(("http://", "https://")):
            return {"success": False, "error": "URL missing http:// or https:// prefix"}
        from backend.integrations.prowlarr import ProwlarrClient
        return await ProwlarrClient().test_connection()

    async def _check_tmdb() -> dict[str, Any]:
        if not config.tmdb.api_key:
            return {"success": False, "error": "Disabled"}
        from backend.integrations.tmdb import TMDBClient
        return await TMDBClient().test_connection()

    async def _check_indexer(idx) -> dict[str, Any]:
        if not idx.name or not idx.url:
            return {"name": idx.name or "Unnamed", "success": False, "error": "Missing name or URL"}
        if not idx.url.startswith(("http://", "https://")):
            return {"name": idx.name, "success": False, "error": "Invalid URL"}
        try:
            from backend.integrations.newznab import NewznabClient
            status = await NewznabClient(idx).test_connection()
            return {"name": idx.name, "success": status.get("success", False), "error": status.get("error")}
        except Exception as e:
            return {"name": idx.name, "success": False, "error": str(e)}

    service_checks = [
        _safe_check("plex", _check_plex),
        _safe_check("sabnzbd", _check_sabnzbd),
        _safe_check("nzbget", _check_nzbget),
        _safe_check("radarr", _check_radarr),
        _safe_check("sonarr", _check_sonarr),
        _safe_check("prowlarr", _check_prowlarr),
        _safe_check("tmdb", _check_tmdb),
    ]

    results = dict(await asyncio.gather(*service_checks))
    indexer_checks = [
        _check_indexer(idx)
        for idx in config.indexers
        if idx.name or idx.url
    ]
    indexer_results = await asyncio.gather(*indexer_checks) if indexer_checks else []
    results["indexers"] = indexer_results

    _services_health_cache = results
    _services_health_cache_at = time.monotonic()
    return results


@router.get("/health/services")
async def services_health(user=Depends(get_current_user)):
    return await _build_services_health()


def _integration_status(raw: dict[str, Any], *, enabled: bool, configured: bool) -> str:
    if raw.get("success"):
        return "connected"
    if not enabled:
        return "disabled"
    if not configured:
        return "unavailable"
    return "degraded"


@router.get("/integrations/matrix", response_model=IntegrationMatrixResponse)
async def integration_matrix(user=Depends(get_current_user)):
    """Return user-facing integration state, purpose, and dependency hints."""
    from backend.config import get_config
    from backend.integrations.download_client import get_active_download_client_name

    config = get_config()
    health = await _build_services_health()
    active_client = get_active_download_client_name()
    indexers = health.get("indexers", [])
    healthy_indexers = [
        idx for idx in indexers
        if isinstance(idx, dict) and idx.get("success")
    ] if isinstance(indexers, list) else []

    services = [
        {
            "key": "plex",
            "name": "Plex",
            "required": True,
            "active": True,
            "purpose": "Source of library items, file paths, sizes, and refresh after replacement.",
            "status": _integration_status(
                health.get("plex", {}),
                enabled=True,
                configured=bool(config.plex.url and config.plex.token),
            ),
            "detail": health.get("plex", {}),
        },
        {
            "key": "radarr",
            "name": "Radarr",
            "required": False,
            "active": bool(config.radarr.enabled),
            "purpose": "Keeps movie metadata in sync after Slimarr replaces a file.",
            "status": _integration_status(
                health.get("radarr", {}),
                enabled=bool(config.radarr.enabled),
                configured=bool(config.radarr.url and config.radarr.api_key),
            ),
            "detail": health.get("radarr", {}),
        },
        {
            "key": "sonarr",
            "name": "Sonarr",
            "required": False,
            "active": bool(config.sonarr.enabled),
            "purpose": "Prevents deleted TV shows from being re-downloaded when unmonitoring is requested.",
            "status": _integration_status(
                health.get("sonarr", {}),
                enabled=bool(config.sonarr.enabled),
                configured=bool(config.sonarr.url and config.sonarr.api_key),
            ),
            "detail": health.get("sonarr", {}),
        },
        {
            "key": "prowlarr",
            "name": "Prowlarr",
            "required": False,
            "active": bool(config.prowlarr.enabled),
            "purpose": "Preferred search bridge across all configured Usenet indexers.",
            "status": _integration_status(
                health.get("prowlarr", {}),
                enabled=bool(config.prowlarr.enabled),
                configured=bool(config.prowlarr.url and config.prowlarr.api_key),
            ),
            "detail": health.get("prowlarr", {}),
        },
        {
            "key": "sabnzbd",
            "name": "SABnzbd",
            "required": active_client == "sabnzbd",
            "active": active_client == "sabnzbd",
            "purpose": "Downloads accepted replacement NZBs and reports completion storage paths.",
            "status": _integration_status(
                health.get("sabnzbd", {}),
                enabled=active_client == "sabnzbd",
                configured=bool(config.sabnzbd.url and config.sabnzbd.api_key),
            ),
            "detail": health.get("sabnzbd", {}),
        },
        {
            "key": "nzbget",
            "name": "NZBGet",
            "required": active_client == "nzbget",
            "active": active_client == "nzbget",
            "purpose": "Alternative Usenet downloader for accepted replacement NZBs.",
            "status": _integration_status(
                health.get("nzbget", {}),
                enabled=active_client == "nzbget",
                configured=bool(config.nzbget.url),
            ),
            "detail": health.get("nzbget", {}),
        },
        {
            "key": "tmdb",
            "name": "TMDB",
            "required": True,
            "active": True,
            "purpose": "Enriches library records with posters, backdrops, IDs, and metadata.",
            "status": _integration_status(
                health.get("tmdb", {}),
                enabled=True,
                configured=bool(config.tmdb.api_key),
            ),
            "detail": health.get("tmdb", {}),
        },
        {
            "key": "indexers",
            "name": "Direct Indexers",
            "required": not config.prowlarr.enabled,
            "active": bool(config.indexers),
            "purpose": "Direct Newznab search fallback when Prowlarr is disabled or returns no results.",
            "status": "connected" if healthy_indexers else ("disabled" if not config.indexers else "degraded"),
            "detail": {"configured": len(config.indexers), "healthy": len(healthy_indexers), "indexers": indexers},
        },
    ]

    active_services = [item for item in services if item["active"] or item["required"]]
    unavailable = [item for item in active_services if item["status"] in {"degraded", "unavailable"}]
    if any(item["required"] and item["status"] != "connected" for item in active_services):
        overall = "unavailable"
    elif unavailable:
        overall = "degraded"
    else:
        overall = "connected"

    return {
        "status": overall,
        "active_download_client": active_client,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }


@router.get("/health/matrix", response_model=HealthMatrixResponse)
async def health_matrix(user=Depends(get_current_user)):
    """Return end-to-end health for app, DB, scheduler, queue, and integrations."""
    components: dict[str, dict[str, Any]] = {
        "api": {"status": "healthy", "detail": "HTTP API reachable"},
    }

    try:
        async with async_session() as db:
            movies_total = (await db.execute(select(func.count()).select_from(Movie))).scalar_one()
            active_downloads = (
                await db.execute(
                    select(func.count()).select_from(Download).where(
                        Download.status.in_(["queued", "downloading", "processing"])
                    )
                )
            ).scalar_one()
        components["database"] = {
            "status": "healthy",
            "detail": "Connected",
            "movies_total": int(movies_total),
        }
        components["queue"] = {
            "status": "healthy",
            "detail": f"{int(active_downloads)} active downloads",
            "active_downloads": int(active_downloads),
        }
    except Exception as e:
        components["database"] = {"status": "down", "detail": str(e)}
        components["queue"] = {"status": "down", "detail": "Unavailable while database is down"}

    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        components["scheduler"] = {"status": "healthy", "detail": "Scheduler running"}
    elif scheduler:
        components["scheduler"] = {"status": "degraded", "detail": "Scheduler initialized but not running"}
    else:
        components["scheduler"] = {"status": "down", "detail": "Scheduler unavailable"}

    cycle = get_status()
    if cycle.get("running"):
        components["orchestrator"] = {"status": "healthy", "detail": "Cycle currently running"}
    elif cycle.get("stop_requested"):
        components["orchestrator"] = {"status": "degraded", "detail": "Stop requested"}
    else:
        components["orchestrator"] = {"status": "healthy", "detail": "Idle"}

    from backend.core.search_diagnostics import degradation_status

    search_state = degradation_status()
    if search_state.get("degraded"):
        components["search_pipeline"] = {
            "status": "degraded",
            "detail": "; ".join(search_state.get("reasons") or ["Search degraded"]),
            **search_state,
        }
    else:
        components["search_pipeline"] = {
            "status": "healthy",
            "detail": "No search degradation detected",
            **search_state,
        }

    recycle_path = _get_recycling_bin_path()
    if not recycle_path:
        components["recycling_bin"] = {"status": "disabled", "detail": "Not configured"}
    elif await asyncio.to_thread(os.path.isdir, recycle_path):
        files_count, bytes_count = await _dir_stats_cached(recycle_path)
        components["recycling_bin"] = {
            "status": "healthy",
            "detail": "Configured",
            "path": recycle_path,
            "files": files_count,
            "bytes": bytes_count,
        }
    else:
        components["recycling_bin"] = {
            "status": "degraded",
            "detail": "Configured path does not exist",
            "path": recycle_path,
        }

    try:
        from backend.core.storage import refresh_nas_policy_usage, storage_operation_snapshot

        await refresh_nas_policy_usage()
        storage_snapshot = storage_operation_snapshot(redact_paths=True, limit=10)
        storage_counters = storage_snapshot.get("counters", {})
        nas_policy = storage_snapshot.get("nas_policy", {})
        recent_failed = storage_snapshot.get("recent_failures", [])
        failure_window = int(storage_snapshot.get("recent_failure_window_seconds", 3600) or 3600)
        failed_total = int(storage_counters.get("move:failed", 0) or 0) + int(
            storage_counters.get("remove:failed", 0) or 0
        )
        if nas_policy.get("cooldown_active"):
            components["storage_operations"] = {
                "status": "degraded",
                "detail": "NAS storage operations are in failure cooldown",
                "cooldown_remaining_seconds": nas_policy.get("cooldown_remaining_seconds", 0),
                "active_operations": nas_policy.get("active_operations", 0),
                "recent_failed": recent_failed[:3],
                "counters": storage_counters,
            }
        elif recent_failed:
            components["storage_operations"] = {
                "status": "degraded",
                "detail": f"{len(recent_failed)} storage operation failure(s) in the last {failure_window // 60} minutes",
                "active_operations": nas_policy.get("active_operations", 0),
                "recent_failed": recent_failed[:3],
                "recent_failure_window_seconds": failure_window,
                "failed_total": failed_total,
                "counters": storage_counters,
            }
        else:
            components["storage_operations"] = {
                "status": "healthy",
                "detail": "Storage operation guard is ready",
                "active_operations": nas_policy.get("active_operations", 0),
                "history_size": storage_snapshot.get("history_size", 0),
                "write_bytes_used_24h": nas_policy.get("write_bytes_used_24h", 0),
                "replacements_24h": nas_policy.get("replacements_24h", 0),
                "counters": storage_counters,
            }
    except Exception as exc:
        components["storage_operations"] = {
            "status": "down",
            "detail": f"Storage operation telemetry unavailable: {exc}",
        }

    try:
        recovery_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
        async with async_session() as db:
            recovery_rows = (
                await db.execute(
                    select(ReplacementRecoveryRecord)
                    .where(ReplacementRecoveryRecord.status.in_(["running", "recovery_required"]))
                    .order_by(
                        ReplacementRecoveryRecord.updated_at.desc(),
                        ReplacementRecoveryRecord.id.desc(),
                    )
                    .limit(10)
                )
            ).scalars().all()
        recovery_required = [
            row for row in recovery_rows if row.status == "recovery_required"
        ]
        stale_running = [
            row
            for row in recovery_rows
            if row.status == "running" and row.updated_at and row.updated_at <= recovery_cutoff
        ]
        if recovery_required or stale_running:
            components["replacement_recovery"] = {
                "status": "degraded",
                "detail": (
                    f"{len(recovery_required)} recovery-required, "
                    f"{len(stale_running)} stale running replacement(s)"
                ),
                "records": [
                    _replacement_recovery_payload(row, redact_paths=True)
                    for row in (recovery_required + stale_running)[:5]
                ],
            }
        elif recovery_rows:
            components["replacement_recovery"] = {
                "status": "healthy",
                "detail": f"{len(recovery_rows)} replacement operation(s) currently tracked",
                "records": [
                    _replacement_recovery_payload(row, redact_paths=True)
                    for row in recovery_rows[:5]
                ],
            }
        else:
            components["replacement_recovery"] = {
                "status": "healthy",
                "detail": "No replacement recovery issues",
                "records": [],
            }
    except Exception as exc:
        components["replacement_recovery"] = {
            "status": "degraded",
            "detail": f"Replacement recovery metadata unavailable: {exc}",
        }

    try:
        from backend.database import JobRecord

        async with async_session() as db:
            status_rows = (
                await db.execute(
                    select(JobRecord.status, func.count(JobRecord.id)).group_by(JobRecord.status)
                )
            ).all()
        job_counts = {str(status): int(count or 0) for status, count in status_rows}
        failed = job_counts.get("failed", 0)
        recovery_required = job_counts.get("recovery_required", 0)
        active = sum(job_counts.get(status, 0) for status in ("queued", "running", "cancelling"))
        if recovery_required or failed:
            components["jobs"] = {
                "status": "degraded",
                "detail": f"{recovery_required} recovery-required, {failed} failed job(s)",
                "counts": job_counts,
            }
        elif active:
            components["jobs"] = {
                "status": "healthy",
                "detail": f"{active} active persistent job(s)",
                "counts": job_counts,
            }
        else:
            components["jobs"] = {
                "status": "healthy",
                "detail": "No active persistent jobs",
                "counts": job_counts,
            }
    except Exception as exc:
        components["jobs"] = {
            "status": "degraded",
            "detail": f"Persistent job telemetry unavailable: {exc}",
        }

    integration_results = await _build_services_health()
    integration_summary = {"healthy": 0, "down": 0, "disabled": 0}
    for key, value in integration_results.items():
        if key == "indexers":
            continue
        success = bool(value.get("success")) if isinstance(value, dict) else False
        error = value.get("error") if isinstance(value, dict) else None
        if success:
            integration_summary["healthy"] += 1
        elif error in {"Disabled", "Not configured", "Missing URL or API key"}:
            integration_summary["disabled"] += 1
        else:
            integration_summary["down"] += 1

    components["integrations"] = {
        "status": "healthy" if integration_summary["down"] == 0 else "degraded",
        "detail": (
            f"{integration_summary['healthy']} healthy, "
            f"{integration_summary['down']} down, "
            f"{integration_summary['disabled']} disabled"
        ),
        "summary": integration_summary,
    }

    try:
        from backend.config import get_config
        from backend.database import Recommendation, StreamingAvailability
        from backend.core.recommendations.streaming import is_stale as availability_is_stale

        rec_config = get_config().recommendations
        if not rec_config.enabled:
            components["recommendations"] = {"status": "disabled", "detail": "Not enabled"}
        else:
            async with async_session() as db:
                active_count = (
                    await db.execute(
                        select(func.count()).select_from(Recommendation).where(Recommendation.state == "active")
                    )
                ).scalar_one()
                latest_availability = (
                    await db.execute(
                        select(StreamingAvailability.checked_at)
                        .order_by(StreamingAvailability.checked_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

            issues: list[str] = []
            if not rec_config.region:
                issues.append("no region configured — streaming availability disabled")
            if latest_availability and availability_is_stale(latest_availability):
                issues.append("streaming availability cache is stale")

            components["recommendations"] = {
                "status": "degraded" if issues else "healthy",
                "detail": "; ".join(issues) if issues else f"{int(active_count)} active recommendation(s)",
                "active_count": int(active_count),
                "region_configured": bool(rec_config.region),
                "ai_enabled": bool(rec_config.ai.enabled),
                "last_availability_check": (
                    latest_availability.isoformat() if latest_availability else None
                ),
            }
    except Exception as exc:
        components["recommendations"] = {
            "status": "degraded",
            "detail": f"Recommendation telemetry unavailable: {exc}",
        }

    down_count = sum(1 for comp in components.values() if comp.get("status") == "down")
    degraded_count = sum(1 for comp in components.values() if comp.get("status") == "degraded")
    overall = "healthy"
    if down_count > 0:
        overall = "down"
    elif degraded_count > 0:
        overall = "degraded"

    return {
        "status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }


@router.get("/decision-audit", response_model=list[DecisionAuditItem])
async def decision_audit(limit: int = 50, decision: str = "", user=Depends(get_current_user)):
    """Return recent comparison decisions with rationale."""
    limit = max(1, min(limit, 500))
    query = select(DecisionAuditLog).order_by(DecisionAuditLog.created_at.desc()).limit(limit)
    normalized_decision = (decision or "").strip().lower()
    if normalized_decision in {"accept", "reject"}:
        query = (
            select(DecisionAuditLog)
            .where(DecisionAuditLog.decision == normalized_decision)
            .order_by(DecisionAuditLog.created_at.desc())
            .limit(limit)
        )

    async with async_session() as db:
        rows = (await db.execute(query)).scalars().all()

    return [
        {
            "id": row.id,
            "movie_id": row.movie_id,
            "movie_title": row.movie_title,
            "indexer_name": row.indexer_name,
            "release_title": row.release_title,
            "candidate_size": row.candidate_size,
            "local_size": row.local_size,
            "decision": row.decision,
            "score": row.score,
            "confidence_score": row.confidence_score,
            "confidence_breakdown": _json_object(row.confidence_breakdown),
            "media_health_score": row.media_health_score,
            "media_health_rating": row.media_health_rating,
            "media_health_reasons": _json_string_list(row.media_health_reasons),
            "savings_bytes": row.savings_bytes,
            "savings_pct": row.savings_pct,
            "reject_reason": row.reject_reason,
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/nas-pressure", response_model=NasPressureResponse)
async def nas_pressure(user=Depends(get_current_user)):
    """Summarize recent NAS-targeted write pressure and policy effectiveness."""
    from backend.config import get_config
    from backend.core.storage import configured_nas_prefixes, is_nas_path

    cfg = get_config()
    nas_prefixes = configured_nas_prefixes(cfg)
    min_savings_mb_for_nas = max(0, int(getattr(cfg.comparison, "min_savings_mb_for_nas", 0) or 0))
    nas_policy_enabled = bool(
        nas_prefixes
        and (
            min_savings_mb_for_nas > 0
            or float(getattr(cfg.files, "nas_max_write_gb_per_day", 0) or 0) > 0
            or int(getattr(cfg.files, "nas_max_replacements_per_day", 0) or 0) > 0
            or float(getattr(cfg.files, "nas_max_transfer_mbps", 0) or 0) > 0
        )
    )

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    replacements_24h = 0
    replacement_bytes_24h = 0
    movie_rollup: dict[str, dict[str, int | str]] = {}

    async with async_session() as db:
        replacement_rows = (
            await db.execute(
                select(ActivityLog)
                .where(
                    ActivityLog.event == "replace:completed",
                    ActivityLog.created_at >= since,
                )
                .order_by(ActivityLog.created_at.desc())
            )
        ).scalars().all()

        for row in replacement_rows:
            target_path = row.new_file_path or row.old_file_path
            if not is_nas_path(target_path, nas_prefixes):
                continue
            replacements_24h += 1
            replacement_bytes_24h += int(row.new_size or 0)
            title = str(row.movie_title or "Unknown")
            if title not in movie_rollup:
                movie_rollup[title] = {"title": title, "count": 0, "written_bytes": 0}
            movie_rollup[title]["count"] = int(movie_rollup[title]["count"]) + 1
            movie_rollup[title]["written_bytes"] = int(movie_rollup[title]["written_bytes"]) + int(row.new_size or 0)

        # Only the count of NAS-floor rejections is needed here, so filter and
        # count in SQL instead of pulling every reject_reason string in the
        # window into Python — with a large decision_audit_log table (one row
        # per candidate evaluated, potentially thousands per night) fetching
        # and iterating the full text of every reject in the last 24h was
        # taking several seconds on an endpoint polled every 60s.
        nas_rejects_24h = (
            await db.execute(
                select(func.count()).select_from(DecisionAuditLog).where(
                    DecisionAuditLog.decision == "reject",
                    DecisionAuditLog.created_at >= since,
                    DecisionAuditLog.reject_reason.like("%NAS minimum%"),
                )
            )
        ).scalar_one()

    top_movies = sorted(
        movie_rollup.values(),
        key=lambda item: (int(item.get("count", 0)), int(item.get("written_bytes", 0))),
        reverse=True,
    )[:5]

    pressure_state = "low"
    if replacements_24h >= 12 or replacement_bytes_24h >= 250 * 1024 * 1024 * 1024:
        pressure_state = "high"
    elif replacements_24h >= 5 or replacement_bytes_24h >= 80 * 1024 * 1024 * 1024:
        pressure_state = "medium"

    recommended_preset = "balanced"
    if pressure_state == "high":
        recommended_preset = "gentle"
    elif pressure_state == "low" and not nas_prefixes:
        recommended_preset = "aggressive"

    recommendations: list[str] = []
    if not nas_prefixes:
        recommendations.append("Add NAS path prefixes (for example Z:/Movies) in Settings to track network-share pressure accurately.")
    if min_savings_mb_for_nas <= 0:
        recommendations.append("Enable NAS savings floor by setting Minimum Savings for NAS Paths (MB) above 0.")
    if pressure_state == "high":
        recommendations.append("Apply the Gentle NAS preset to lower scan and write churn during peak periods.")
    elif pressure_state == "medium":
        recommendations.append("Balanced NAS preset is recommended to keep upgrades steady without bursty write activity.")
    else:
        recommendations.append("Current NAS pressure is low; you can keep current settings or use Aggressive only if NAS remains stable.")

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "pressure_state": pressure_state,
        "recommended_preset": recommended_preset,
        "nas_prefixes": nas_prefixes,
        "nas_policy_enabled": nas_policy_enabled,
        "recent": {
            "replacements_24h": replacements_24h,
            "replacement_bytes_24h": replacement_bytes_24h,
            "nas_rejects_24h": nas_rejects_24h,
            "unique_movies_replaced_24h": len(movie_rollup),
        },
        "top_movies": top_movies,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Self-update
# ---------------------------------------------------------------------------
_update_lock = False  # prevent concurrent updates


@router.post("/update", response_model=ActionStatusResponse)
async def trigger_update(background: BackgroundTasks, user=Depends(get_current_user)):
    """
    Pull latest code from GitHub, install new dependencies, then signal the
    watchdog (run.py) to restart the server by exiting with code 42.
    Progress is streamed to the frontend via Socket.IO events.
    """
    global _update_lock
    if _update_lock:
        return {"status": "already_running"}
    _update_lock = True
    background.add_task(_run_update)
    return {"status": "started"}


async def _run_update() -> None:
    global _update_lock
    import asyncio
    from loguru import logger
    from backend.realtime.events import emit_event

    async def _emit(line: str, level: str = "info") -> None:
        await emit_event("update:log", {"line": line, "level": level})
        logger.info(f"[update] {line}")

    try:
        # backend/api/system.py -> backend/api -> backend -> project root
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        python = sys.executable

        await _emit("Starting update...")

        # 1. git pull
        await _emit("Running git pull...")
        git_result = await asyncio.create_subprocess_exec(
            "git", "pull", "--ff-only",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in git_result.stdout:
            await _emit(raw.decode(errors="replace").rstrip())
        await git_result.wait()
        if git_result.returncode != 0:
            await _emit(f"git pull failed (exit {git_result.returncode})", "error")
            await emit_event("update:failed", {"reason": "git pull failed"})
            return

        # 2. pip install -r requirements.txt
        await _emit("Installing dependencies...")
        pip_result = await asyncio.create_subprocess_exec(
            python, "-m", "pip", "install", "-r", os.path.join(root, "requirements.txt"), "--quiet",
            cwd=root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in pip_result.stdout:
            line = raw.decode(errors="replace").rstrip()
            if line:
                await _emit(line)
        await pip_result.wait()
        if pip_result.returncode != 0:
            await _emit(f"pip install failed (exit {pip_result.returncode})", "error")
            await emit_event("update:failed", {"reason": "pip install failed"})
            return

        await _emit("Update complete — restarting server...")
        await emit_event("update:restarting", {})
        # Give the WebSocket event time to reach the client before we exit
        await asyncio.sleep(1.5)
        # Signal the watchdog to restart (os._exit bypasses asyncio cleanup)
        os._exit(42)

    except Exception as e:
        await emit_event("update:failed", {"reason": str(e)})
        logger.error(f"Update failed: {e}")
    finally:
        _update_lock = False
