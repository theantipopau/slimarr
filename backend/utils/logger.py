"""Loguru logger configuration.

Logging behaviour adapts automatically to the runtime environment:

* **Docker / headless (no TTY)**: structured plain-text lines to stderr,
  suitable for ``docker logs`` and log aggregators.  Set
  ``SLIMARR_LOG_FORMAT=json`` to emit newline-delimited JSON instead.
* **Interactive terminal**: colourised human-readable output.
* **File**: rotating compressed log with full timestamps.

Environment variables
---------------------
SLIMARR_LOG_LEVEL   Override log level (DEBUG/INFO/WARNING/ERROR).
SLIMARR_LOG_FORMAT  ``json`` for JSON sink on stderr; default is plain text.
SLIMARR_LOG_FILE    Override the log file path (default: data/logs/slimarr.log).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timezone

from loguru import logger


def _inject_correlation_id(record: dict) -> None:
    """Attach correlation ID from request context to every log record."""
    cid = "-"
    try:
        from backend.utils.responses import get_correlation_id

        value = get_correlation_id()
        if value:
            cid = value
    except Exception:
        pass
    record["extra"]["cid"] = cid


def _json_serializer(record: dict) -> str:
    """Render a loguru record as a compact JSON line for structured logging."""
    subset = {
        "time": record["time"].astimezone(timezone.utc).isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "cid": record["extra"].get("cid", "-"),
        "message": record["message"],
    }
    if record.get("exception"):
        import traceback
        subset["exception"] = "".join(
            traceback.format_exception(*record["exception"])
        ).strip()
    return json.dumps(subset, ensure_ascii=False)


def _is_docker_or_ci() -> bool:
    """Heuristic: no real TTY → treat output as machine-readable."""
    if not sys.stderr.isatty():
        return True
    try:
        from backend.utils.platform import is_docker
        return is_docker()
    except Exception:
        return False


def setup_logger(
    log_level: str = "INFO",
    log_file: str = "data/logs/slimarr.log",
) -> None:
    # Allow env-var overrides so Docker Compose / Kubernetes can tune verbosity
    # without touching config.yaml.
    log_level = os.environ.get("SLIMARR_LOG_LEVEL", log_level).upper()
    log_file = os.environ.get("SLIMARR_LOG_FILE", log_file)
    log_format = os.environ.get("SLIMARR_LOG_FORMAT", "plain").lower()

    logger.remove()
    logger.configure(patcher=_inject_correlation_id)

    if sys.stderr is not None:
        if log_format == "json":
            # Structured JSON lines — best for log aggregators (Loki, Splunk, ELK)
            logger.add(
                sys.stderr,
                level=log_level,
                colorize=False,
                serialize=False,
                format="{message}",  # _json_sink handles actual formatting
            )
            # Replace with a custom sink that emits JSON
            logger.remove()
            logger.configure(patcher=_inject_correlation_id)
            logger.add(
                _JsonStderrSink(),
                level=log_level,
                format="{message}",
                colorize=False,
            )
        elif _is_docker_or_ci():
            # Plain structured text — no ANSI colour codes, Docker-friendly
            logger.add(
                sys.stderr,
                level=log_level,
                colorize=False,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[cid]} | {name} - {message}",
            )
        else:
            # Interactive terminal — colourised
            logger.add(
                sys.stderr,
                level=log_level,
                colorize=True,
                format=(
                    "<green>{time:HH:mm:ss}</green> | "
                    "<level>{level: <8}</level> | "
                    "<magenta>{extra[cid]}</magenta> | "
                    "<cyan>{name}</cyan> - <level>{message}</level>"
                ),
            )

    # Rotating compressed file log (always enabled unless log_file is empty)
    if log_file:
        logger.add(
            log_file,
            level=log_level,
            rotation="10 MB",
            retention="14 days",
            compression="gz",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[cid]} | {name} - {message}",
        )

    logger.info(f"Logger initialised — level={log_level} format={log_format}")


class _JsonStderrSink:
    """Custom loguru sink that writes JSON lines to stderr."""

    def write(self, message: "loguru.Message") -> None:  # type: ignore[name-defined]
        record = message.record
        line = _json_serializer(record)
        sys.stderr.write(line + "\n")
        sys.stderr.flush()

    def __call__(self, message: "loguru.Message") -> None:  # type: ignore[name-defined]
        self.write(message)
