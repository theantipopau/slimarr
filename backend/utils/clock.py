"""UTC timestamps shared across the backend.

The naive variant matches the SQLite DATETIME columns, which store UTC without tzinfo.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
