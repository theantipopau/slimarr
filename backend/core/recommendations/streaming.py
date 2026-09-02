"""Streaming availability via TMDB's /watch/providers endpoint.

Region-specific, explicitly opt-in (no region configured = no lookups at
all), cached with an expiry, and never presented as current once stale — the
caller checks `is_stale` rather than this module silently returning old data
as if it were fresh. TMDB requires attribution (a link to their site) for
this data, which is why source_url is stored per row (see
docs/RECOMMENDATION_ARCHITECTURE.md's StreamingAvailability model / TMDB's
own API terms).

No streaming service is scraped or hard-coded — every provider TMDB reports
is stored; `subscribed_providers` in config only affects which ones a
recommendation's score treats as "yours", not which ones this module fetches.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from loguru import logger

from backend.integrations.tmdb import TMDBClient, TMDBError

# TMDB's own attribution requirement — every response must link back to the
# region-specific listing page, not just the show/movie page.
_TMDB_ATTRIBUTION_URL_TEMPLATE = "https://www.themoviedb.org/{media_type}/{tmdb_id}/watch?locale={region}"

_AVAILABILITY_TYPE_MAP = {
    "flatrate": "flatrate",
    "ads": "ads",
    "free": "free",
    "rent": "rent",
    "buy": "buy",
}

_CACHE_TTL_HOURS = 24


@dataclass(frozen=True)
class AvailabilityEntry:
    provider_id: int
    provider_name: str
    display_priority: int | None
    availability_type: str
    region: str
    source: str
    source_url: str
    checked_at: datetime
    expires_at: datetime


def _parse_region_block(region: str, media_type: str, tmdb_id: int, block: dict) -> list[AvailabilityEntry]:
    now = _utc_now()
    expires = now + timedelta(hours=_CACHE_TTL_HOURS)
    attribution = _TMDB_ATTRIBUTION_URL_TEMPLATE.format(media_type=media_type, tmdb_id=tmdb_id, region=region)
    entries: list[AvailabilityEntry] = []
    for availability_type, entry_list in block.items():
        mapped_type = _AVAILABILITY_TYPE_MAP.get(availability_type)
        if not mapped_type or not isinstance(entry_list, list):
            continue
        for item in entry_list:
            provider_id = item.get("provider_id")
            provider_name = item.get("provider_name")
            if not provider_id or not provider_name:
                continue
            entries.append(AvailabilityEntry(
                provider_id=provider_id,
                provider_name=provider_name,
                display_priority=item.get("display_priority"),
                availability_type=mapped_type,
                region=region,
                source="tmdb",
                source_url=attribution,
                checked_at=now,
                expires_at=expires,
            ))
    return entries


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def fetch_availability(
    *, tmdb: TMDBClient, tmdb_id: int, media_type: str, region: str
) -> list[AvailabilityEntry]:
    """Returns an empty list (not an exception) if the region has no listed
    providers or if TMDB has no watch/providers data for this title at all —
    both are normal, common outcomes, not error conditions."""
    if not region:
        # Explicit-region requirement: never silently assume one.
        return []

    try:
        payload = await tmdb.get_watch_providers(tmdb_id, media_type=media_type)
    except TMDBError as exc:
        logger.warning(
            "Streaming availability lookup failed for tmdb_id={} media_type={}: {}",
            tmdb_id, media_type, exc,
        )
        return []

    region_block = (payload.get("results") or {}).get(region.upper())
    if not region_block:
        return []

    return _parse_region_block(region.upper(), media_type, tmdb_id, region_block)


def is_stale(checked_at: datetime, *, now: datetime | None = None) -> bool:
    now = now or _utc_now()
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return (now - checked_at) > timedelta(hours=_CACHE_TTL_HOURS)
