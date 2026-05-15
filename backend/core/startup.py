"""
Startup validation and environment audit for Slimarr v1.4.

Runs once during application startup to:
 - Detect the runtime environment (OS, Docker, architecture)
 - Validate writable data directories
 - Check free disk space
 - Log a structured startup banner
 - Expose the results via get_startup_context() for the /system/info endpoint

No external service calls are made here; those happen in the health matrix.
"""
from __future__ import annotations

import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.utils.platform import (
    container_id,
    disk_free_bytes,
    is_docker,
    is_writable,
    os_info,
    safe_makedirs,
)
from backend.version import APP_VERSION

# ── Startup context (populated once, read many times) ────────────────────────
_startup_context: dict[str, Any] = {}
_startup_warnings: list[str] = []


def get_startup_context() -> dict[str, Any]:
    return _startup_context


def get_startup_warnings() -> list[str]:
    return list(_startup_warnings)


# ── Main entry point ─────────────────────────────────────────────────────────

def run_startup_checks(config_path: str = "config.yaml") -> None:
    """Run all pre-flight checks and populate the startup context.

    Called once from the FastAPI lifespan, before the scheduler starts.
    Logs a startup banner and emits warnings for actionable issues.
    """
    global _startup_context, _startup_warnings

    from backend.config import get_config
    cfg = get_config()

    _startup_warnings = []
    ctx: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "version": APP_VERSION,
    }

    # ── OS / runtime ─────────────────────────────────────────────────────────
    ctx["runtime"] = _check_runtime()

    # ── Data directories ─────────────────────────────────────────────────────
    ctx["directories"] = _check_directories(cfg)

    # ── Disk space ───────────────────────────────────────────────────────────
    ctx["disk"] = _check_disk("data")

    # ── Config summary ───────────────────────────────────────────────────────
    ctx["config"] = _config_summary(cfg, config_path)

    _startup_context = ctx

    _emit_banner(ctx)
    for w in _startup_warnings:
        logger.warning(f"[startup] {w}")


# ── Individual checks ─────────────────────────────────────────────────────────

def _check_runtime() -> dict[str, Any]:
    info = os_info()
    in_docker = is_docker()
    cid = container_id()

    result: dict[str, Any] = {
        "os": info["os"],
        "os_release": info["os_release"],
        "arch": platform.machine(),
        "python": info["python"],
        "in_docker": in_docker,
        "container_id": cid or "",
        "pid": os.getpid(),
    }

    if in_docker:
        logger.info(
            f"[startup] Running in Docker container{f' ({cid})' if cid else ''}"
        )
    else:
        logger.info(
            f"[startup] Running on {info['os']} {info['os_release']} "
            f"({info['machine']}) Python {info['python']}"
        )

    return result


def _check_directories(cfg: Any) -> list[dict[str, Any]]:
    """Ensure required data directories exist and are writable."""
    dirs = [
        ("data", "data"),
        ("logs", "data/logs"),
        ("media_cover", "data/MediaCover"),
    ]
    recycling = (cfg.files.recycling_bin or "").strip()
    if recycling:
        dirs.append(("recycling_bin", recycling))

    results = []
    for label, path in dirs:
        try:
            safe_makedirs(path)
        except OSError as exc:
            _startup_warnings.append(f"Cannot create directory '{path}': {exc}")
            results.append({"label": label, "path": path, "ok": False, "error": str(exc)})
            continue

        writable = is_writable(path)
        if not writable:
            _startup_warnings.append(
                f"Directory '{path}' is not writable. "
                "Check volume permissions (uid/gid)."
            )
        results.append({"label": label, "path": path, "ok": writable})

    return results


def _check_disk(path: str) -> dict[str, Any]:
    """Check free disk space and warn when running low."""
    free = disk_free_bytes(path)
    if free is None:
        return {"path": path, "free_bytes": None, "status": "unknown"}

    free_gb = free / (1024 ** 3)
    if free_gb < 1.0:
        status = "critical"
        _startup_warnings.append(
            f"Very low disk space at '{path}': {free_gb:.2f} GB free. "
            "Downloads may fail."
        )
    elif free_gb < 5.0:
        status = "warn"
        _startup_warnings.append(
            f"Low disk space at '{path}': {free_gb:.2f} GB free."
        )
    else:
        status = "ok"

    return {"path": path, "free_bytes": free, "free_gb": round(free_gb, 2), "status": status}


def _config_summary(cfg: Any, config_path: str) -> dict[str, Any]:
    """Collect non-secret config facts for the startup banner."""
    providers: list[str] = []
    if cfg.plex.url:
        providers.append("plex")
    if cfg.prowlarr.enabled and cfg.prowlarr.url:
        providers.append("prowlarr")
    if cfg.radarr.enabled and cfg.radarr.url:
        providers.append("radarr")
    if cfg.sonarr.enabled and cfg.sonarr.url:
        providers.append("sonarr")
    if cfg.tmdb.api_key:
        providers.append("tmdb")
    for idx in cfg.indexers:
        if idx.url:
            providers.append(f"indexer:{idx.name or idx.url}")

    config_exists = os.path.exists(config_path)
    env_overrides = [
        k for k in os.environ
        if k.startswith("SLIMARR_") and k not in ("SLIMARR_SECRET_KEY", "SLIMARR_API_KEY")
    ]

    return {
        "config_file": config_path,
        "config_file_exists": config_exists,
        "env_overrides": env_overrides,
        "active_providers": providers,
        "download_client": cfg.download_client,
        "schedule_mode": cfg.schedule.mode,
        "dry_run": cfg.automation.dry_run,
        "port": cfg.server.port,
    }


def _emit_banner(ctx: dict[str, Any]) -> None:
    rt = ctx["runtime"]
    cfg = ctx["config"]
    disk = ctx["disk"]

    providers_str = ", ".join(cfg["active_providers"]) or "none configured"
    env_count = len(cfg.get("env_overrides", []))
    disk_str = f"{disk.get('free_gb', '?')} GB free" if disk.get("free_gb") is not None else "unknown"

    logger.info("=" * 60)
    logger.info(f"  Slimarr v{APP_VERSION} starting up")
    logger.info(f"  OS:         {rt['os']} {rt['os_release']} ({rt['arch']})")
    logger.info(f"  Python:     {rt['python']}")
    logger.info(f"  Docker:     {rt['in_docker']}")
    logger.info(f"  Port:       {cfg['port']}")
    logger.info(f"  Providers:  {providers_str}")
    logger.info(f"  Dry-run:    {cfg['dry_run']}")
    logger.info(f"  Disk (data):{disk_str}")
    if env_count:
        logger.info(f"  Env overrides: {env_count} active")
    logger.info("=" * 60)
