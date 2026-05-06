"""Utilities for evaluating configured schedule windows in local/user timezone."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from backend.config import SlimarrConfig

_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _parse_time(value: str, fallback: str) -> time:
    raw = (value or fallback).strip()
    try:
        hour_s, minute_s = raw.split(":", 1)
        return time(hour=int(hour_s), minute=int(minute_s))
    except Exception:
        hour_s, minute_s = fallback.split(":", 1)
        return time(hour=int(hour_s), minute=int(minute_s))


def get_schedule_timezone(config: SlimarrConfig):
    tz_name = (getattr(config.schedule, "timezone", "local") or "local").strip()
    if tz_name.lower() in {"", "local", "system"}:
        return datetime.now().astimezone().tzinfo
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return datetime.now().astimezone().tzinfo


def is_within_schedule_window(config: SlimarrConfig, now: datetime | None = None) -> bool:
    """
    Check whether current local/user time is inside schedule.start_time <= t < schedule.end_time.
    Supports windows spanning midnight, such as 23:00 -> 05:00.
    """
    tz = get_schedule_timezone(config)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    start_t = _parse_time(config.schedule.start_time, "01:00")
    end_t = _parse_time(config.schedule.end_time, "07:00")
    now_t = now.time().replace(second=0, microsecond=0)
    spans_midnight = end_t <= start_t

    allowed_days = {
        str(d).strip().lower()[:3]
        for d in (config.schedule.days or [])
        if str(d).strip().lower()[:3] in _VALID_DAYS
    }
    if not allowed_days:
        allowed_days = set(_VALID_DAYS)

    if not spans_midnight:
        if not (start_t <= now_t < end_t):
            return False
        anchor_day = now.strftime("%a").lower()[:3]
        return anchor_day in allowed_days

    if now_t >= start_t:
        anchor_day = now.strftime("%a").lower()[:3]
        return anchor_day in allowed_days

    if now_t < end_t:
        anchor_day = (now - timedelta(days=1)).strftime("%a").lower()[:3]
        return anchor_day in allowed_days

    return False
