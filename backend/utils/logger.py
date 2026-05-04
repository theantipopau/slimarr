"""Loguru logger configuration."""
from __future__ import annotations

import sys

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
        # Keep logging resilient even when request context is unavailable.
        pass
    record["extra"]["cid"] = cid


def setup_logger(log_level: str = "INFO", log_file: str = "data/logs/slimarr.log") -> None:
    logger.remove()
    logger.configure(patcher=_inject_correlation_id)
    logger.add(sys.stderr, level=log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <magenta>{extra[cid]}</magenta> | <cyan>{name}</cyan> - <level>{message}</level>")
    logger.add(
        log_file,
        level=log_level,
        rotation="10 MB",
        retention="14 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[cid]} | {name} - {message}",
    )
    logger.info(f"Logger initialised — level={log_level}")
