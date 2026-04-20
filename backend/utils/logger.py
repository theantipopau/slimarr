"""Loguru logger configuration."""
from __future__ import annotations

import sys

from loguru import logger


def setup_logger(log_level: str = "INFO", log_file: str = "data/logs/slimarr.log") -> None:
    logger.remove()
    logger.add(sys.stderr, level=log_level, colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>")
    logger.add(
        log_file,
        level=log_level,
        rotation="10 MB",
        retention="14 days",
        compression="gz",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} - {message}",
    )
    logger.info(f"Logger initialised — level={log_level}")
