"""Plex/Radarr/Sonarr state correlation for the recommendation engine.

Fetches Radarr's/Sonarr's full library ONCE per refresh run into an in-memory
snapshot, rather than once per candidate — RadarrClient.find_movie_by_imdb()
fetches Radarr's entire movie list per call (see
docs/BACKEND_AND_RECOMMENDATIONS_AUDIT.md finding, "Optional improvements"),
and a recommendation refresh evaluates far more candidates per run than the
replacement pipeline ever calls Radarr for. This module is the fix for that
specific hot-path concern, without touching RadarrClient itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select

from backend.database import Movie, async_session


@dataclass(frozen=True)
class CorrelationSnapshot:
    plex_tmdb_ids: frozenset[int] = frozenset()
    plex_imdb_ids: frozenset[str] = frozenset()
    radarr_imdb_ids: frozenset[str] = frozenset()
    sonarr_titles: frozenset[str] = field(default_factory=frozenset)  # normalized (lower/stripped)


async def _plex_owned_ids() -> tuple[frozenset[int], frozenset[str]]:
    async with async_session() as db:
        rows = (
            await db.execute(select(Movie.tmdb_id, Movie.imdb_id).where(Movie.tmdb_id.is_not(None)))
        ).all()
    tmdb_ids = frozenset(row[0] for row in rows if row[0])
    imdb_ids = frozenset(row[1] for row in rows if row[1])
    return tmdb_ids, imdb_ids


async def _radarr_owned_imdb_ids(config) -> frozenset[str]:
    if not (config.radarr.enabled and config.radarr.url and config.radarr.api_key):
        return frozenset()
    try:
        from backend.integrations.radarr import RadarrClient

        movies = await RadarrClient().get_movies()
        return frozenset(m["imdbId"] for m in movies if m.get("imdbId"))
    except Exception as exc:
        logger.warning("Recommendation correlation: Radarr snapshot failed, treating as empty: {}", exc)
        return frozenset()


async def _sonarr_owned_titles(config) -> frozenset[str]:
    if not (config.sonarr.enabled and config.sonarr.url and config.sonarr.api_key):
        return frozenset()
    try:
        from backend.integrations.sonarr import SonarrClient

        series = await SonarrClient().get_all_series()
        return frozenset(s["title"].strip().lower() for s in series if s.get("title"))
    except Exception as exc:
        logger.warning("Recommendation correlation: Sonarr snapshot failed, treating as empty: {}", exc)
        return frozenset()


async def build_correlation_snapshot(config) -> CorrelationSnapshot:
    plex_tmdb_ids, plex_imdb_ids = await _plex_owned_ids()
    radarr_imdb_ids = await _radarr_owned_imdb_ids(config)
    sonarr_titles = await _sonarr_owned_titles(config)
    return CorrelationSnapshot(
        plex_tmdb_ids=plex_tmdb_ids,
        plex_imdb_ids=plex_imdb_ids,
        radarr_imdb_ids=radarr_imdb_ids,
        sonarr_titles=sonarr_titles,
    )


def is_in_plex(snapshot: CorrelationSnapshot, *, tmdb_id: int | None, imdb_id: str | None) -> bool:
    if tmdb_id and tmdb_id in snapshot.plex_tmdb_ids:
        return True
    if imdb_id and imdb_id in snapshot.plex_imdb_ids:
        return True
    return False


def is_managed_in_radarr(snapshot: CorrelationSnapshot, *, imdb_id: str | None) -> bool:
    return bool(imdb_id and imdb_id in snapshot.radarr_imdb_ids)


def is_managed_in_sonarr(snapshot: CorrelationSnapshot, *, title: str | None) -> bool:
    # Exact-match only, deliberately — the same conservatism as
    # SonarrClient.unmonitor_series_by_title()'s exact-match-first behavior.
    # A false-negative here just means an already-owned show gets suggested
    # once more (low cost, user dismisses it); a false-positive fuzzy match
    # would incorrectly suppress a genuinely-missing show forever.
    return bool(title and title.strip().lower() in snapshot.sonarr_titles)
